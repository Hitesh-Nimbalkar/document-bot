




/**
 * Upload Management Module
 * Handles direct S3 uploads via Lambda (Base64 encoded)
 */
class UploadManager {
    constructor(sessionManager, modelManager, uiManager) {
        this.sessionManager = sessionManager;
        this.modelManager = modelManager;
        this.uiManager = uiManager;
        this.isUploading = false;
        this.uploadedFiles = []; // Store upload response data for processing step
        this.STORAGE_KEY = 'document_bot_upload_responses'; // Local storage key
    }
    async uploadSelectedFiles() {
        if (!this.uiManager.selectedFiles.length) {
            this.showError("Please select files to upload");
            return;
        }
        const projectName = document.getElementById("projectNameInput")?.value.trim();
        if (!projectName) {
            this.showError("Please enter a project name");
            return;
        }
        this.isUploading = true;
        const uploadBtn = document.getElementById("uploadBtn");
        const progressBar = document.getElementById("uploadProgressBar");
        const uploadStatus = document.getElementById("uploadStatus");
        const dropZone = document.getElementById("dropZone");
        if (uploadBtn) uploadBtn.disabled = true;
        if (progressBar) {
            progressBar.style.width = "0%";
            progressBar.innerText = "0%";
        }
        if (uploadStatus) uploadStatus.innerHTML = "";
        try {
            this.uploadedFiles = []; // Clear previous upload data
            this.clearLocalStorageUploadData(); // Clear previous stored responses
            for (let i = 0; i < this.uiManager.selectedFiles.length; i++) {
                const file = this.uiManager.selectedFiles[i];
                const uploadResult = await this.uploadSingleFile(file, projectName);
                
                // Store the EXACT Lambda response
                this.uploadedFiles.push(uploadResult);
                const percent = Math.round(((i + 1) / this.uiManager.selectedFiles.length) * 100);
                if (progressBar) {
                    progressBar.style.width = `${percent}%`;
                    progressBar.innerText = `${percent}%`;
                }
                if (uploadStatus) {
                    uploadStatus.innerHTML = `<div class="text-info">
                        Uploading ${file.name} (${i + 1}/${this.uiManager.selectedFiles.length})
                    </div>`;
                }
            }
            if (uploadStatus) {
                uploadStatus.innerHTML = `<div class="text-success">✅ All files uploaded successfully!</div>`;
            }
            if (dropZone) {
                dropZone.classList.remove("uploading");
                dropZone.classList.add("success");
            }
            console.log("📦 Upload responses stored:", this.uploadedFiles);
            
            // Store responses in localStorage for persistence
            this.saveToLocalStorage();
            
            setTimeout(() => {
                this.uiManager.resetUploadForm();
                if (projectName) this.uiManager.loadProjectFiles(projectName);
            }, 2000);
        } catch (err) {
            console.error("Upload failed:", err);
            if (uploadStatus) {
                uploadStatus.innerHTML = `<div class="text-danger">❌ Upload failed: ${err.message}</div>`;
            }
            if (dropZone) {
                dropZone.classList.remove("uploading");
                dropZone.classList.add("error");
            }
        } finally {
            if (uploadBtn) uploadBtn.disabled = false;
            this.isUploading = false;
        }
    }
    async uploadSingleFile(file, projectName) {
        if (!this.sessionManager?.isValidSession()) {
            throw new Error("No valid session. Please login again.");
        }
        
        // Check file size before processing (30MB limit to account for base64 exncoding)
        const MAX_FILE_SIZE = 30 * 1024 * 1024; // 30MB in bytes
        if (file.size > MAX_FILE_SIZE) {
            throw new Error(`File "${file.name}" is too large (${(file.size / (1024 * 1024)).toFixed(1)}MB). Maximum allowed size is 30MB.`);
        }
        
        // Convert file → Base64
        const fileBase64 = await this.readFileAsBase64(file);
        
        // Get selected embedding model information
        const embeddingPayload = this.modelManager?.getSelectedEmbeddingModelPayload() || {};
        console.log("🔍 Debug - embeddingPayload:", embeddingPayload);
        console.log("🔍 Debug - modelManager exists:", !!this.modelManager);
        console.log("🔍 Debug - hasSelectedModel:", this.modelManager?.hasSelectedModel());
        
        // Ensure we always have embedding fields - critical for backend validation
        const embedding_provider = embeddingPayload.embedding_provider || "bedrock";
        const embedding_model = embeddingPayload.embedding_model || "amazon.titan-embed-text-v2:0";
        
        // Build payload
        const payload = {
            project_name: projectName,
            file_name: file.name,
            content_type: file.type || this.getContentTypeFromExtension(file.name),
            file_content: fileBase64, // ✅ send file as base64
            session_id: this.sessionManager.currentSession.sessionId,
            user_id: this.sessionManager.currentSession.user?.username || "unknown",
            // Add embedding model information - guaranteed to be present
            embedding_provider: embedding_provider,
            embedding_model: embedding_model
        };
        console.log("🔍 Debug - Final payload keys:", Object.keys(payload));
        console.log("🔍 Debug - embedding_provider value:", payload.embedding_provider);
        console.log("🔍 Debug - embedding_model value:", payload.embedding_model);
        console.log("📤 Uploading via Lambda:", payload);
        const response = await makeApiRequest(
            window.API_ENDPOINTS.GET_PRESIGNED_URL, // still using same route
            payload
        );
        const responseBody = typeof response.body === "string"
            ? JSON.parse(response.body)
            : response.body || response;
        // Check if upload was successful based on statusCode instead of success field
        if (response.statusCode !== 200) {
            throw new Error(responseBody.error || "Upload failed at Lambda");
        }
        console.log(`✅ Uploaded to S3: ${file.name}`);
        // Return the COMPLETE RAW Lambda response - NO modifications!
        return response;
    }
    readFileAsBase64(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result.split(",")[1]); // remove prefix like data:...
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    }
    getContentTypeFromExtension(fileName) {
        const ext = fileName.split(".").pop()?.toLowerCase();
        const map = {
            pdf: "application/pdf",
            doc: "application/msword",
            docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            txt: "text/plain",
            csv: "text/csv",
            xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            xls: "application/vnd.ms-excel"
        };
        return map[ext] || "application/octet-stream";
    }
    // Methods for Lambda response storage (core functionality)
    getUploadedFilesData() {
        console.log("🔍 Debug - getUploadedFilesData called");
        console.log("🔍 Debug - uploadedFiles in memory:", this.uploadedFiles.length);
        
        // First try from memory, then from localStorage
        if (this.uploadedFiles && this.uploadedFiles.length > 0) {
            console.log("🔍 Debug - returning from memory:", this.uploadedFiles);
            return this.uploadedFiles;
        }
        
        // Load from localStorage if not in memory
        const fromStorage = this.loadFromLocalStorage();
        console.log("🔍 Debug - loaded from localStorage:", fromStorage.length, fromStorage);
        return fromStorage;
    }
    clearUploadedFilesData() {
        this.uploadedFiles = [];
        this.clearLocalStorageUploadData();
    }
    saveToLocalStorage() {
        try {
            localStorage.setItem(this.STORAGE_KEY, JSON.stringify(this.uploadedFiles));
            console.log("💾 Saved upload responses to localStorage");
        } catch (err) {
            console.error("Failed to save upload responses:", err);
        }
    }
    loadFromLocalStorage() {
        try {
            const stored = localStorage.getItem(this.STORAGE_KEY);
            return stored ? JSON.parse(stored) : [];
        } catch (err) {
            console.error("Failed to load upload responses:", err);
            return [];
        }
    }
    clearLocalStorageUploadData() {
        try {
            localStorage.removeItem(this.STORAGE_KEY);
            console.log("🗑️ Cleared upload responses from localStorage");
        } catch (err) {
            console.error("Failed to clear upload responses:", err);
        }
    }
    // Add error display method
    showError(message) {
        console.error("❌", message);
        const statusDiv = document.getElementById("processingStatus");
        if (statusDiv) {
            statusDiv.style.display = "block";
            statusDiv.innerHTML = `<div class="alert alert-danger">❌ ${message}</div>`;
        } else {
            alert(`Error: ${message}`);
        }
    }
}
// Export globally
window.UploadManager = UploadManager;



