


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
        const projectNameInput = document.getElementById('projectNameInput');
        const fileInput = document.getElementById('fileInput');
        const dropZone = document.getElementById('dropZone');
        if (projectNameInput) {
            projectNameInput.addEventListener('input', this.debouncedLoadProjectFiles.bind(this));
            projectNameInput.addEventListener('blur', this.updateUploadButtonState.bind(this));
        }
        if (fileInput && dropZone) {
            fileInput.addEventListener('change', this.handleFileSelect.bind(this));
            dropZone.addEventListener('click', () => fileInput.click());
            dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
            dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
            dropZone.addEventListener('drop', this.handleFileDrop.bind(this));
        }
    }
    handleFileSelect(event) {
        this.addFilesToSelection(Array.from(event.target.files));
        this.refreshFilesUI();
    }
    handleFileDrop(event) {
        event.preventDefault();
        event.currentTarget.classList.remove('dragover');
        this.addFilesToSelection(Array.from(event.dataTransfer.files));
        this.refreshFilesUI();
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
        this.refreshFilesUI();
    }
    refreshFilesUI() {
        this.displaySelectedFiles();
        this.updateUploadButtonState();
    }
    displaySelectedFiles() {
        const container = document.getElementById('selectedFiles');
        if (!container) return;
        if (this.selectedFiles.length === 0) {
            container.style.display = 'none';
            return;
        }
        container.style.display = 'block';
        container.innerHTML = this.selectedFiles.map((file, i) => `
            <div class="file-item">
                <div class="file-info">
                    <h6>${file.name}</h6>
                    <div class="file-size">${this.formatFileSize(file.size)}</div>
                </div>
                <button class="remove-btn" onclick="window.uiManager.removeFile(${i})">
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
        return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`;
    }
    updateUploadButtonState() {
        // Keep buttons always enabled - remove validation logic
        const uploadBtn = document.getElementById('uploadBtn');
        const processBtn = document.getElementById('processDocsBtn');
        
        if (uploadBtn) uploadBtn.disabled = false;
        if (processBtn) processBtn.disabled = false;
    }
    
    updateProcessButtonState() {
        // Keep process button always enabled - remove validation logic
        const processBtn = document.getElementById('processDocsBtn');
        if (processBtn) processBtn.disabled = false;
    }
    
    debouncedLoadProjectFiles() {
        clearTimeout(this.debounceTimer);
        this.debounceTimer = setTimeout(() => {
            const projectName = document.getElementById('projectNameInput')?.value.trim();
            if (projectName) this.loadProjectFiles(projectName);
            else this.displayProjectFiles([]);
        }, 500);
    }
    async loadProjectFiles(projectName) {
        try {
            const session = this.sessionManager.getSession();
            if (!session?.sessionId) return;
            const payload = {
                project_name: projectName,
                session_id: session.sessionId,
                user_id: session.user?.username || 'unknown'
            };
            const response = await fetch(buildApiUrl(API_ENDPOINTS.LIST_PROJECT_FILES), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
                body: JSON.stringify(payload)
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            const files = typeof data.body === 'string' ? JSON.parse(data.body).files : data.body?.files || [];
            this.displayProjectFiles(files);
        } catch {
            this.displayProjectFiles([]);
        }
    }
    displayProjectFiles(files) {
        const section = document.getElementById('existingFilesSection');
        const list = document.getElementById('filesList');
        const count = document.getElementById('filesCount');
        if (!section || !list || !count) return;
        if (!files.length) {
            section.style.display = 'none';
            return;
        }
        section.style.display = 'block';
        count.textContent = `${files.length} file${files.length !== 1 ? 's' : ''}`;
        list.innerHTML = files.map(file => `
            <div class="existing-file-item">
                <div class="file-icon ${this.getFileIcon(file.key?.split('.').pop() || 'txt')}">
                    ${(file.key?.split('.').pop() || 'txt').toUpperCase()}
                </div>
                <div class="flex-grow-1">
                    <h6 class="mb-1">${file.key?.split('/').pop() || 'Unknown'}</h6>
                    <small class="text-muted">
                        ${file.size ? this.formatFileSize(file.size) : 'Unknown size'} • 
                        ${file.last_modified ? new Date(file.last_modified).toLocaleString() : 'Unknown date'}
                    </small>
                </div>
            </div>
        `).join('');
    }
    getFileIcon(ext) {
        const map = { pdf: 'pdf', doc: 'doc', docx: 'doc', txt: 'txt', csv: 'csv', xlsx: 'xlsx', xls: 'xlsx' };
        return map[ext.toLowerCase()] || 'txt';
    }
    resetUploadForm() {
        this.selectedFiles = [];
        this.displaySelectedFiles();
        const fileInput = document.getElementById('fileInput');
        if (fileInput) fileInput.value = '';
        const dropZone = document.getElementById('dropZone');
        if (dropZone) dropZone.classList.remove('uploading', 'success', 'error');
        const progress = document.querySelector('.progress');
        if (progress) progress.style.display = 'none';
        this.updateUploadButtonState();
    }
    clearSelectedFiles() {
        this.selectedFiles = [];
        this.displaySelectedFiles();
        const fileInput = document.getElementById('fileInput');
        if (fileInput) fileInput.value = '';
        const selectedFilesSection = document.getElementById('selectedFiles');
        if (selectedFilesSection) selectedFilesSection.style.display = 'none';
        this.updateUploadButtonState();
    }
    // Add error display method
    showError(message) {
        console.error("❌", message);
        
        // Try to show in processing status div first
        const statusDiv = document.getElementById("processingStatus");
        if (statusDiv) {
            statusDiv.style.display = "block";
            statusDiv.innerHTML = `<div class="alert alert-danger">❌ ${message}</div>`;
            return;
        }
        
        // Fallback to alert
        alert(`Error: ${message}`);
    }
}
window.UIManager = UIManager;


