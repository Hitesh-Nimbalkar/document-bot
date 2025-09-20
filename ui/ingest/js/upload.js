/**
 * Upload Management Module
 * Handles file uploads via presigned URLs
 */
class UploadManager {
    constructor(sessionManager, modelManager, uiManager) {
        this.sessionManager = sessionManager;
        this.modelManager = modelManager;
        this.uiManager = uiManager;
    }
    async uploadFiles() {
        const projectName = document.getElementById('projectNameInput')?.value.trim();
        const selectedEmbeddingModel = this.modelManager.getSelectedEmbeddingModelPayload();
        
        if (!projectName || this.uiManager.selectedFiles.length === 0) {
            this.uiManager.showError('Please enter a project name and select files to upload');
            return;
        }
        
        if (!selectedEmbeddingModel) {
            this.uiManager.showError('Please select an embedding model before uploading files');
            return;
        }
        const uploadBtn = document.getElementById('uploadBtn');
        const dropZone = document.getElementById('dropZone');
        const progress = document.querySelector('.progress');
        const progressBar = document.getElementById('uploadProgress');
        const uploadStatus = document.getElementById('uploadStatus');
        if (uploadBtn) uploadBtn.disabled = true;
        if (dropZone) dropZone.classList.add('uploading');
        if (progress) progress.style.display = 'block';
        if (uploadStatus) uploadStatus.style.display = 'block';
        try {
            for (let i = 0; i < this.uiManager.selectedFiles.length; i++) {
                const file = this.uiManager.selectedFiles[i];
                const progressPercent = ((i + 1) / this.uiManager.selectedFiles.length) * 100;
                
                if (progressBar) progressBar.style.width = `${progressPercent}%`;
                if (uploadStatus) {
                    uploadStatus.innerHTML = `
                        <div class="text-info">
                            <i class="fas fa-spinner fa-spin me-2"></i>
                            Uploading ${file.name} (${i + 1}/${this.uiManager.selectedFiles.length})
                        </div>
                    `;
                }
                await this.uploadSingleFile(file, projectName);
            }
            // Success
            if (dropZone) {
                dropZone.classList.remove('uploading');
                dropZone.classList.add('success');
            }
            if (uploadStatus) {
                uploadStatus.innerHTML = `
                    <div class="text-success">
                        <i class="fas fa-check-circle me-2"></i>
                        All files uploaded successfully!
                    </div>
                `;
            }
            // Reset after 3 seconds
            setTimeout(() => {
                this.uiManager.resetUploadForm();
                // Reload project files to show the newly uploaded files
                const projectName = document.getElementById('projectNameInput')?.value.trim();
                if (projectName) {
                    this.uiManager.loadProjectFiles(projectName);
                } else {
                    this.loadUploadHistory();
                }
            }, 3000);
        } catch (error) {
            if (dropZone) {
                dropZone.classList.remove('uploading');
                dropZone.classList.add('error');
            }
            if (uploadStatus) {
                uploadStatus.innerHTML = `
                    <div class="text-danger">
                        <i class="fas fa-exclamation-circle me-2"></i>
                        Upload failed: ${error.message}
                    </div>
                `;
            }
            if (uploadBtn) uploadBtn.disabled = false;
        }
    }
    async uploadSingleFile(file, projectName) {
        try {
            // Verify session is still valid
            if (!this.sessionManager.isValidSession()) {
                throw new Error('No valid session found. Please login again.');
            }
            // Step 1: Get presigned URL
            const presignedPayload = {
                project_name: projectName,
                file_name: file.name,
                content_type: file.type || this.getContentTypeFromExtension(file.name),
                session_id: this.sessionManager.currentSession.sessionId,
                user_id: this.sessionManager.currentSession.user?.username || 'unknown'
            };
            // Add embedding model parameters
            const embeddingModelPayload = this.modelManager.getSelectedEmbeddingModelPayload();
            if (embeddingModelPayload) {
                Object.assign(presignedPayload, embeddingModelPayload);
                console.log('📊 Including embedding model in presigned URL request:', embeddingModelPayload);
            }
            console.log('📤 Sending presigned URL request:', {
                project: projectName,
                file: file.name,
                sessionId: presignedPayload.session_id,
                userId: presignedPayload.user_id
            });
            const presignedUrlResponse = await fetch(buildApiUrl(API_ENDPOINTS.GET_PRESIGNED_URL), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...this.sessionManager.getAuthHeaders()
                },
                body: JSON.stringify(presignedPayload)
            });
            if (!presignedUrlResponse.ok) {
                throw new Error(`Failed to get presigned URL: ${presignedUrlResponse.statusText}`);
            }
            const presignedData = await presignedUrlResponse.json();
            const responseBody = typeof presignedData.body === 'string' ? 
                JSON.parse(presignedData.body) : presignedData.body || presignedData;
            if (!responseBody.success) {
                throw new Error(responseBody.error || 'Failed to get presigned URL');
            }
            // Step 2: Upload to S3 using presigned POST
            const formData = new FormData();
            
            // Add all the required fields from presigned URL
            Object.keys(responseBody.fields).forEach(key => {
                formData.append(key, responseBody.fields[key]);
            });
            
            // Add the file last
            formData.append('file', file);
            const uploadResponse = await fetch(responseBody.upload_url, {
                method: 'POST',
                body: formData
            });
            if (!uploadResponse.ok) {
                const errorText = await uploadResponse.text();
                throw new Error(`Upload failed: ${uploadResponse.statusText} - ${errorText}`);
            }
            console.log(`✅ Successfully uploaded: ${file.name}`);
            
            // Add to upload history
            this.addToUploadHistory({
                fileName: file.name,
                projectName: projectName,
                uploadTime: new Date().toISOString(),
                fileSize: file.size
            });
        } catch (error) {
            console.error(`❌ Failed to upload ${file.name}:`, error);
            throw error;
        }
    }
    getContentTypeFromExtension(fileName) {
        const extension = fileName.split('.').pop()?.toLowerCase();
        const contentTypes = {
            'pdf': 'application/pdf',
            'doc': 'application/msword',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'txt': 'text/plain',
            'csv': 'text/csv',
            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'xls': 'application/vnd.ms-excel'
        };
        return contentTypes[extension] || 'application/octet-stream';
    }
    addToUploadHistory(uploadRecord) {
        try {
            const history = JSON.parse(localStorage.getItem('uploadHistory') || '[]');
            history.unshift(uploadRecord); // Add to beginning
            
            // Keep only last 50 uploads
            if (history.length > 50) {
                history.splice(50);
            }
            
            localStorage.setItem('uploadHistory', JSON.stringify(history));
        } catch (error) {
            console.error('Failed to save upload history:', error);
        }
    }
    loadUploadHistory() {
        try {
            const history = JSON.parse(localStorage.getItem('uploadHistory') || '[]');
            // You can implement history display here if needed
            console.log('📚 Upload history:', history);
            return history;
        } catch (error) {
            console.error('Failed to load upload history:', error);
            return [];
        }
    }
}
// Export for use in other modules
window.UploadManager = UploadManager;
