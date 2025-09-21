
/**
 * Model Management Module
 * Handles loading and managing embedding models from JSON configuration
 */
class ModelManager {
    constructor() {
        this.availableModels = {};
        this.selectedModel = null;
        this.boundOnChange = null;
    }
    async loadEmbeddingModels() {
        try {
            const response = await fetch('models.json');
            if (!response.ok) throw new Error(`Failed to load models.json: ${response.status}`);
            const models = await response.json();
            this.availableModels = models;
            if (models.embeddings && typeof models.embeddings === 'object') {
                this.populateModelDropdown(models.embeddings);
            } else {
                this.setDefaultModel();
            }
        } catch {
            this.setDefaultModel();
        }
    }
    populateModelDropdown(embeddings) {
        const select = document.getElementById('embeddingModelSelect');
        if (!select) return;
        select.innerHTML = '<option value="">-- Select Embedding Model --</option>';
        Object.entries(embeddings || {}).forEach(([key, model]) => {
            if (!model) return;
            const providerDisplay = model.provider === 'aws_bedrock'
                ? 'AWS Bedrock'
                : model.provider === 'openai'
                ? 'OpenAI'
                : model.provider.toUpperCase();
            const option = document.createElement('option');
            option.value = key;
            option.textContent = `${key} - ${providerDisplay} (${model.vector_size}D)`;
            option.dataset.modelData = JSON.stringify({
                ...model,
                key,
                identifier: model.model_id || model.model_name || key,
                provider_display: providerDisplay
            });
            select.appendChild(option);
        });
        if (!this.boundOnChange) {
            this.boundOnChange = this.onModelSelectionChange.bind(this);
        }
        select.removeEventListener('change', this.boundOnChange);
        select.addEventListener('change', this.boundOnChange);
    }
    onModelSelectionChange(event) {
        const selectedOption = event.target.selectedOptions[0];
        if (selectedOption && selectedOption.value) {
            this.selectedModel = JSON.parse(selectedOption.dataset.modelData);
            this.showModelInfo(this.selectedModel);
        } else {
            this.selectedModel = null;
            this.hideModelInfo();
        }
        // Update both upload and process button states
        if (window.uiManager) {
            window.uiManager.updateUploadButtonState();
            window.uiManager.updateProcessButtonState();
        }
    }
    showModelInfo(model) {
        const infoDiv = document.getElementById('modelInfo');
        const detailsDiv = document.getElementById('modelDetails');
        if (!infoDiv || !detailsDiv) return;
        const providerDisplay = model.provider_display || model.provider;
        const modelId = model.model_id || model.model_name || model.key;
        detailsDiv.innerHTML = `
            <div class="row g-2">
                <div class="col-md-6">
                    <strong>Provider:</strong> ${providerDisplay}<br>
                    <strong>Model:</strong> ${modelId}
                </div>
                <div class="col-md-6">
                    <strong>Vector Size:</strong> ${model.vector_size}D<br>
                    <strong>Context:</strong> ${model.context_length.toLocaleString()} tokens
                </div>
            </div>
            <div class="mt-1">
                <strong>Use Case:</strong> ${model.recommended_use || 'N/A'}
            </div>
        `;
        infoDiv.style.display = 'block';
    }
    hideModelInfo() {
        const infoDiv = document.getElementById('modelInfo');
        if (infoDiv) infoDiv.style.display = 'none';
    }
    getSelectedEmbeddingModelPayload() {
        const select = document.getElementById('embeddingModelSelect');
        const selectedOption = select?.selectedOptions[0];
        if (!selectedOption?.dataset.modelData) return null;
        const modelData = JSON.parse(selectedOption.dataset.modelData);
        return {
            embedding_provider: modelData.provider === 'aws_bedrock' ? 'bedrock' : modelData.provider,
            embedding_model: modelData.identifier,
            embedding_model_key: modelData.key,
            vector_size: modelData.vector_size,
            context_length: modelData.context_length,
            provider_display: modelData.provider_display
        };
    }
    setDefaultModel() {
        this.availableModels = {
            embeddings: {
                titan_v2: {
                    provider: 'aws_bedrock',
                    model_id: 'amazon.titan-embed-text-v2:0',
                    vector_size: 1536,
                    context_length: 8000,
                    recommended_use: 'General text semantic search, RAG'
                }
            }
        };
        this.populateModelDropdown(this.availableModels.embeddings);
    }
    hasSelectedModel() {
        return this.getSelectedEmbeddingModelPayload() !== null;
    }
}
// Export globally
window.ModelManager = ModelManager;

