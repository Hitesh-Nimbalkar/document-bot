
/**
 * Data Ingestion Module
 * Handles document processing and ingestion
 */
class DataIngestionManager {
    constructor(sessionManager, modelManager, uiManager) {
        this.sessionManager = sessionManager;
        this.modelManager = modelManager;
        this.uiManager = uiManager;
    }
    async processDocuments() {
        const projectName = document.getElementById('projectNameInput')?.value.trim();
        const selectedEmbeddingModel = this.modelManager.getSelectedEmbeddingModelPayload();
        if (!projectName) {
            this.uiManager.showError('Please enter a project name');
            return;
        }
        if (!this.uiManager.projectFiles || this.uiManager.projectFiles.length === 0) {
            this.uiManager.showError('No files found in project to process');
            return;
        }
        if (!selectedEmbeddingModel) {
            this.uiManager.showError('Please select an embedding model');
            return;
        }
        if (!this.sessionManager.isValidSession()) {
            this.uiManager.showError('Session expired. Please login again.');
            return;
        }
        console.log('🚀 Starting document processing...');
        this.showProcessingStatus(true);
        try {
            // Prepare document locations from project files
            const docLocations = this.uiManager.projectFiles.map(file => ({
                key: file.key,
                size: file.size,
                last_modified: file.last_modified
            }));
            // Build the payload for data ingestion
            const payload = {
                session_id: this.sessionManager.currentSession.sessionId,
                project_name: projectName,
                user_id: this.sessionManager.currentSession.user?.username || 'unknown',
                doc_locs: docLocations,
                ...selectedEmbeddingModel // Include embedding model parameters
            };
            console.log('📤 Data ingestion payload:', payload);
            // Call the data ingestion API
            const response = await fetch(buildApiUrl(API_ENDPOINTS.DATA_INGESTION), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...this.sessionManager.getAuthHeaders()
                },
                body: JSON.stringify(payload)
            });
            if (!response.ok) {
                throw new Error(`Data ingestion failed: ${response.status} ${response.statusText}`);
            }
            const result = await response.json();
            const responseBody = typeof result.body === 'string' ? 
                JSON.parse(result.body) : result.body || result;
            if (responseBody.success) {
                console.log('✅ Document processing completed successfully');
                this.showProcessingResult(true, responseBody);
            } else {
                throw new Error(responseBody.error || 'Document processing failed');
            }
        } catch (error) {
            console.error('❌ Document processing failed:', error);
            this.showProcessingResult(false, { error: error.message });
        } finally {
            this.showProcessingStatus(false);
        }
    }
    showProcessingStatus(isProcessing) {
        const processingStatus = document.getElementById('processingStatus');
        const processBtn = document.getElementById('processDocsBtn');
        if (!processingStatus) return;
        if (isProcessing) {
            processingStatus.style.display = 'block';
            processingStatus.innerHTML = `
                <div class="card">
                    <div class="card-body">
                        <h6><i class="fas fa-spinner fa-spin me-2"></i>Processing Documents...</h6>
                        <div class="progress mb-2">
                            <div class="progress-bar progress-bar-striped progress-bar-animated" 
                                 role="progressbar" style="width: 100%"></div>
                        </div>
                        <small class="text-muted">
                            Extracting text, generating embeddings, and indexing documents for search...
                        </small>
                    </div>
                </div>
            `;
            if (processBtn) processBtn.disabled = true;
        } else {
            if (processBtn) processBtn.disabled = false;
        }
    }
    showProcessingResult(success, result) {
        const processingStatus = document.getElementById('processingStatus');
        if (!processingStatus) return;
        if (success) {
            processingStatus.innerHTML = `
                <div class="card border-success">
                    <div class="card-body">
                        <h6 class="text-success">
                            <i class="fas fa-check-circle me-2"></i>Processing Completed Successfully!
                        </h6>
                        <div class="mt-3">
                            ${this.formatProcessingResults(result)}
                        </div>
                        <div class="mt-3">
                            <button class="btn btn-success" onclick="window.location.href='../dashboard.html'">
                                <i class="fas fa-search me-2"></i>Go to Search Dashboard
                            </button>
                        </div>
                    </div>
                </div>
            `;
        } else {
            processingStatus.innerHTML = `
                <div class="card border-danger">
                    <div class="card-body">
                        <h6 class="text-danger">
                            <i class="fas fa-exclamation-triangle me-2"></i>Processing Failed
                        </h6>
                        <div class="text-muted mt-2">
                            ${result.error || 'An unknown error occurred'}
                        </div>
                        <div class="mt-3">
                            <button class="btn btn-outline-primary" onclick="window.dataIngestionManager.processDocuments()">
                                <i class="fas fa-redo me-2"></i>Retry Processing
                            </button>
                        </div>
                    </div>
                </div>
            `;
        }
        // Auto-hide after 10 seconds if successful
        if (success) {
            setTimeout(() => {
                if (processingStatus) {
                    processingStatus.style.display = 'none';
                }
            }, 10000);
        }
    }
    formatProcessingResults(result) {
        let summary = '<div class="row g-3">';
        
        if (result.processed_documents) {
            summary += `
                <div class="col-md-4">
                    <div class="text-center">
                        <h5 class="text-primary">${result.processed_documents}</h5>
                        <small class="text-muted">Documents Processed</small>
                    </div>
                </div>
            `;
        }
        if (result.total_chunks) {
            summary += `
                <div class="col-md-4">
                    <div class="text-center">
                        <h5 class="text-info">${result.total_chunks}</h5>
                        <small class="text-muted">Text Chunks Created</small>
                    </div>
                </div>
            `;
        }
        if (result.processing_time) {
            summary += `
                <div class="col-md-4">
                    <div class="text-center">
                        <h5 class="text-success">${result.processing_time}s</h5>
                        <small class="text-muted">Processing Time</small>
                    </div>
                </div>
            `;
        }
        summary += '</div>';
        if (result.embedding_model) {
            summary += `
                <div class="mt-3 pt-3 border-top">
                    <small class="text-muted">
                        <strong>Embedding Model:</strong> ${result.embedding_model}<br>
                        <strong>Vector Dimensions:</strong> ${result.vector_size || 'N/A'}
                    </small>
                </div>
            `;
        }
        return summary;
    }
    // Method to check processing status (if backend supports it)
    async checkProcessingStatus(taskId) {
        try {
            const response = await fetch(buildApiUrl(API_ENDPOINTS.PROCESSING_STATUS), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...this.sessionManager.getAuthHeaders()
                },
                body: JSON.stringify({ task_id: taskId })
            });
            if (response.ok) {
                const result = await response.json();
                return result;
            }
        } catch (error) {
            console.error('Failed to check processing status:', error);
        }
        return null;
    }
}
// Export for use in other modules
window.DataIngestionManager = DataIngestionManager;
