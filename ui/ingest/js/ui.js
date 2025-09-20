/**
 * UI Management Module
 * Handles form validation, button states, and general UI updates
 */
class UIManager {
    constructor(sessionManager, modelManager) {
        this.sessionManager = sessionManager;
        this.modelManager = modelManager;
        this.selectedFiles = [];
        this.projectFiles = [];
        this.debounceTimer = null;
    }

    initializeEventListeners() {
        // Project name input
        const projectNameInput = document.getElementById('projectNameInput');
        if (projectNameInput) {
            projectNameInput.addEventListener('input', this.debouncedLoadProjectFiles.bind(this));
            projectNameInput.addEventListener('blur', this.updateUploadButtonState.bind(this));
        }

        // File input and drag/drop
        const fileInput = document.getElementById('fileInput');
        const dropZone = document.getElementById('dropZone');
        
        if (fileInput && dropZone) {
            fileInput.addEventListener('change', this.handleFileSelect.bind(this));
            
            dropZone.addEventListener('click', () => fileInput.click());
            dropZone.addEventListener('dragover', this.handleDragOver.bind(this));
            dropZone.addEventListener('dragleave', this.handleDragLeave.bind(this));
            dropZone.addEventListener('drop', this.handleFileDrop.bind(this));
        }
    }

    handleFileSelect(event) {
        const files = Array.from(event.target.files);
        this.addFilesToSelection(files);
        this.displaySelectedFiles();
        this.updateUploadButtonState();
    }

    handleDragOver(event) {
        event.preventDefault();
        event.currentTarget.classList.add('dragover');
    }

    handleDragLeave(event) {
        event.currentTarget.classList.remove('dragover');
    }

    handleFileDrop(event) {
        event.preventDefault();
        const dropZone = event.currentTarget;
        dropZone.classList.remove('dragover');
        
        const files = Array.from(event.dataTransfer.files);
        this.addFilesToSelection(files);
        this.displaySelectedFiles();
        this.updateUploadButtonState();
    }

    addFilesToSelection(files) {
        files.forEach(file => {
            if (!this.selectedFiles.find(f => f.name === file.name && f.size === file.size)) {
                this.selectedFiles.push(file);
            }
        });
    }

    removeFile(index) {
        this.selectedFiles.splice(index, 1);
        this.displaySelectedFiles();
        this.updateUploadButtonState();
        
        if (this.selectedFiles.length === 0) {
            const fileInput = document.getElementById('fileInput');
            if (fileInput) fileInput.value = '';
        }
    }

    displaySelectedFiles() {
        const container = document.getElementById('selectedFiles');
        if (!container) return;
        if (this.selectedFiles.length === 0) {
            container.style.display = 'none';
            return;
        }
        container.style.display = 'block';
        container.innerHTML = this.selectedFiles.map((file, index) => `
            <div class="file-item">
                <div class="file-info">
                    <h6>${file.name}</h6>
                    <div class="file-size">${this.formatFileSize(file.size)}</div>
                </div>
                <button class="remove-btn" onclick="window.uiManager.removeFile(${index})">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `).join('');
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    updateUploadButtonState() {
        const uploadBtn = document.getElementById('uploadBtn');
        const processDocsBtn = document.getElementById('processDocsBtn');

        const projectName = document.getElementById('projectNameInput')?.value.trim() || "";
        const hasFiles = this.selectedFiles.length > 0;
        const hasProject = projectName.length >= 3; // at least 3 chars
        const hasEmbeddingModel = window.modelManager?.hasSelectedModel?.() || false;

        console.log("🔎 [UIManager] updateUploadButtonState", {
            projectName,
            hasProject,
            hasFiles,
            hasEmbeddingModel
        });

        // Inline message container
        let statusMsg = document.getElementById("uploadStatusMsg");
        if (!statusMsg) {
            statusMsg = document.createElement("div");
            statusMsg.id = "uploadStatusMsg";
            statusMsg.style.marginTop = "6px";
            statusMsg.style.fontSize = "13px";
            statusMsg.style.color = "red";
            const btnContainer = uploadBtn?.parentNode;
            if (btnContainer) btnContainer.appendChild(statusMsg);
        }

        const reasons = [];
        if (!hasProject) reasons.push("Enter a project name (≥ 3 chars)");
        if (!hasFiles) reasons.push("Select at least one file");
        if (!hasEmbeddingModel) reasons.push("Choose an embedding model");

        if (uploadBtn) {
            if (reasons.length === 0) {
                uploadBtn.disabled = false;
                statusMsg.textContent = "";
                console.log("✅ Upload button ENABLED");
            } else {
                uploadBtn.disabled = true;
                statusMsg.textContent = "⚠️ " + reasons.join(" | ");
                console.warn("⚠️ Upload button DISABLED →", reasons);
            }
        }

        if (processDocsBtn) {
            if (reasons.length === 0) {
                processDocsBtn.disabled = false;
                console.log("✅ Process Documents button ENABLED");
            } else {
                processDocsBtn.disabled = true;
                console.warn("⚠️ Process Documents button DISABLED →", reasons);
            }
        }
    }

    debouncedLoadProjectFiles() {
        if (this.debounceTimer) {
            clearTimeout(this.debounceTimer);
        }
        this.debounceTimer = setTimeout(() => {
            const projectName = document.getElementById('projectNameInput')?.value.trim();
            if (projectName) {
                this.loadProjectFiles(projectName);
            } else {
                this.displayProjectFiles([]);
            }
        }, 500);
    }

    async loadProjectFiles(projectName) {
        try {
            console.log(`📁 Loading files for project: ${projectName}`);
            const currentSession = window.sessionManager?.getSession();
            if (!currentSession?.sessionId) {
                console.warn('No valid session for loading project files');
                return;
            }
            const payload = {
                project_name: projectName,
                session_id: currentSession.sessionId,
                user_id: currentSession.user?.username || 'unknown'
            };
            const response = await fetch(buildApiUrl(API_ENDPOINTS.LIST_PROJECT_FILES), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...getAuthHeaders()
                },
                body: JSON.stringify(payload)
            });
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            const data = await response.json();
            const responseBody = typeof data.body === 'string' ? JSON.parse(data.body) : data.body || data;
            if (responseBody.success && responseBody.files) {
                this.displayProjectFiles(responseBody.files);
            } else {
                this.displayProjectFiles([]);
            }
        } catch (error) {
            console.error('Error loading project files:', error);
            this.displayProjectFiles([]);
        }
    }

    displayProjectFiles(files) {
        const existingFilesSection = document.getElementById('existingFilesSection');
        const filesList = document.getElementById('filesList');
        const filesCount = document.getElementById('filesCount');
        
        if (!existingFilesSection || !filesList || !filesCount) return;
        this.projectFiles = files;
        if (files.length === 0) {
            existingFilesSection.style.display = 'none';
            return;
        }
        existingFilesSection.style.display = 'block';
        filesCount.textContent = `${files.length} file${files.length !== 1 ? 's' : ''}`;
        filesList.innerHTML = files.map(file => {
            const extension = file.key?.split('.').pop()?.toLowerCase() || 'txt';
            const iconClass = this.getFileIcon(extension);
            const fileName = file.key?.split('/').pop() || file.key || 'Unknown';
            const fileSize = file.size ? this.formatFileSize(file.size) : 'Unknown size';
            const lastModified = file.last_modified ? new Date(file.last_modified).toLocaleString() : 'Unknown date';
            return `
                <div class="existing-file-item">
                    <div class="file-icon ${iconClass}">
                        ${extension.toUpperCase()}
                    </div>
                    <div class="flex-grow-1">
                        <h6 class="mb-1">${fileName}</h6>
                        <small class="text-muted">${fileSize} • ${lastModified}</small>
                    </div>
                </div>
            `;
        }).join('');
    }

    getFileIcon(extension) {
        const iconMap = {
            'pdf': 'pdf',
            'doc': 'doc',
            'docx': 'doc',
            'txt': 'txt',
            'csv': 'csv',
            'xlsx': 'xlsx',
            'xls': 'xlsx'
        };
        return iconMap[extension] || 'txt';
    }

    showError(message) {
        console.error('UI Error:', message);
        alert(message);
    }

    showSuccess(message) {
        console.log('UI Success:', message);
    }

    resetUploadForm() {
        this.selectedFiles = [];
        this.displaySelectedFiles();
        
        const fileInput = document.getElementById('fileInput');
        const dropZone = document.getElementById('dropZone');
        const progress = document.querySelector('.progress');
        
        if (fileInput) fileInput.value = '';
        if (dropZone) {
            dropZone.classList.remove('uploading', 'success', 'error');
        }
        if (progress) progress.style.display = 'none';
        
        this.updateUploadButtonState();
    }

    clearSelectedFiles() {
        this.selectedFiles = [];
        this.displaySelectedFiles();
        this.updateUploadButtonState();
        
        const fileInput = document.getElementById('fileInput');
        if (fileInput) fileInput.value = '';
        
        const selectedFilesSection = document.getElementById('selectedFiles');
        if (selectedFilesSection) {
            selectedFilesSection.style.display = 'none';
        }
    }
}

// Export for use in other modules
window.UIManager = UIManager;
