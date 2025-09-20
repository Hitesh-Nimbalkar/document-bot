
/**
 * Model Management Module
 * Handles loading and managing embedding models from JSON configuration
 */
class ModelManager {
    constructor() {
        this.availableModels = {};
        this.selectedModel = null;
        this.boundOnChange = null; // Will be set when needed
    }
    async loadEmbeddingModels() {
        try {
            console.log('📋 Loading embedding models from JSON...');
            const response = await fetch('models.json'); // Fixed path - go up one directory
            
            console.log('🌐 Fetch response status:', response.status, response.statusText);
            
            if (!response.ok) {
                const errorText = await response.text();
                console.error('❌ Fetch error details:', errorText);
                throw new Error(`Failed to load models.json: ${response.status} - ${errorText}`);
            }
            
            const models = await response.json();
            console.log('📋 Raw JSON response:', models);
            console.log('📋 Type of models:', typeof models);
            console.log('📋 Models keys:', Object.keys(models));
            
            this.availableModels = models;
            
            console.log('✅ Loaded models from JSON:', models);
            console.log('📋 Embeddings section exists?', !!models.embeddings);
            console.log('📋 Embeddings section:', models.embeddings);
            console.log('📋 Type of embeddings section:', typeof models.embeddings);
            
            if (models.embeddings && typeof models.embeddings === 'object') {
                console.log('🔑 Embedding model keys:', Object.keys(models.embeddings));
                console.log('🔑 Number of embedding models:', Object.keys(models.embeddings).length);
                
                // Debug each model individually
                Object.keys(models.embeddings).forEach((key, index) => {
                    console.log(`📊 Model ${index + 1} - "${key}":`, models.embeddings[key]);
                });
                
                this.populateModelDropdown(models.embeddings);
            } else {
                console.error('❌ Embeddings section is missing or invalid!');
                this.setDefaultModel();
            }
            console.log('✅ Completed loading embedding models');
            
        } catch (error) {
            console.error('❌ Failed to load models.json:', error);
            this.setDefaultModel();
        }
    }
    populateModelDropdown(embeddings) {
        console.log('🎯 populateModelDropdown called with embeddings:', embeddings);
        const select = document.getElementById('embeddingModelSelect');
        if (!select) {
            console.error('❌ Could not find #embeddingModelSelect element!');
            return;
        }
        // Clear existing options and add default
        select.innerHTML = '<option value="">-- Select Embedding Model --</option>';
        // Ensure embeddings is a valid object
        if (!embeddings || typeof embeddings !== 'object') {
            console.error('❌ Embeddings is missing or not an object:', embeddings);
            return;
        }
        const modelKeys = Object.keys(embeddings);
        console.log(`🔑 Found ${modelKeys.length} model(s):`, modelKeys);
        if (modelKeys.length === 0) {
            console.warn('⚠️ No embedding models found to populate dropdown.');
            return;
        }
        modelKeys.forEach((modelKey, index) => {
            try {
                const model = embeddings[modelKey];
                if (!model) {
                    console.warn(`⚠️ Model ${modelKey} is null/undefined. Skipping.`);
                    return;
                }
                console.log(`\n🔄 Adding model ${index + 1}/${modelKeys.length}: ${modelKey}`, model);
                // Build display name
                const displayName = `${modelKey} (${model.provider}) - ${model.vector_size}D`;
                // Pick an identifier (model_id, model_name, or fallback to key)
                const modelId = model.model_id || model.model_name || modelKey;
                
                // Determine provider display name
                const providerDisplay = model.provider === 'aws_bedrock' ? 'AWS Bedrock' : 
                                      model.provider === 'openai' ? 'OpenAI' : 
                                      model.provider.toUpperCase();
                // Create <option>
                const option = document.createElement('option');
                option.value = modelKey;
                option.textContent = `${modelKey} - ${providerDisplay} (${model.vector_size}D)`;
                option.dataset.modelData = JSON.stringify({
                    ...model,
                    key: modelKey,
                    display_name: displayName,
                    identifier: modelId,
                    provider_display: providerDisplay
                });
                select.appendChild(option);
                console.log(`✅ Added option: ${displayName}`);
            } catch (err) {
                console.error(`❌ Error processing model "${modelKey}":`, err);
            }
        });
        // Final sanity check
        console.log('📊 Final dropdown option count:', select.options.length);
        Array.from(select.options).forEach((opt, i) =>
            console.log(`${i}: value="${opt.value}", text="${opt.textContent}"`)
        );
        // Attach event listener (use bound reference from constructor!)
        if (!this.boundOnChange) {
            this.boundOnChange = this.onModelSelectionChange.bind(this);
        }
        select.removeEventListener('change', this.boundOnChange);
        select.addEventListener('change', this.boundOnChange);
        console.log('🎯 Event listener attached to dropdown');
    }
    onModelSelectionChange(event) {
        const select = event.target;
        const selectedOption = select.selectedOptions[0];
        const processBtn = document.getElementById('processDocsBtn');
        
        if (selectedOption && selectedOption.value) {
            this.selectedModel = JSON.parse(selectedOption.dataset.modelData);
            if (processBtn) processBtn.disabled = false;
            this.showModelInfo(this.selectedModel);
            console.log('🎯 Selected embedding model:', this.selectedModel);
        } else {
            this.selectedModel = null;
            if (processBtn) processBtn.disabled = true;
            this.hideModelInfo();
        }
        
        // Trigger upload button state update
        if (window.uiManager) {
            window.uiManager.updateUploadButtonState();
        }
    }
    showModelInfo(model) {
        const infoDiv = document.getElementById('modelInfo');
        const detailsDiv = document.getElementById('modelDetails');
        
        if (!infoDiv || !detailsDiv) return;
        
        // Map provider to display name
        const providerDisplay = model.provider === 'aws_bedrock' ? 'AWS Bedrock' : 
                              model.provider === 'openai' ? 'OpenAI' : 
                              model.provider.toUpperCase();
        
        const modelId = model.model_id || model.model_name || model.key;
        
        const details = `
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
                <strong>Use Case:</strong> ${model.recommended_use}
            </div>
        `;
        
        detailsDiv.innerHTML = details;
        infoDiv.style.display = 'block';
        
        console.log('📊 Model info displayed:', {
            provider: model.provider,
            model_id: modelId,
            provider_display: providerDisplay
        });
    }
    hideModelInfo() {
        const infoDiv = document.getElementById('modelInfo');
        if (infoDiv) {
            infoDiv.style.display = 'none';
        }
    }
    getSelectedEmbeddingModelPayload() {
        const select = document.getElementById('embeddingModelSelect');
        const selectedOption = select?.selectedOptions[0];
        
        if (selectedOption && selectedOption.value && selectedOption.dataset.modelData) {
            const modelData = JSON.parse(selectedOption.dataset.modelData);
            console.log('🎯 Selected model payload data:', modelData);
            
            // Handle both model_id and model_name properties
            const modelIdentifier = modelData.model_id || modelData.model_name || modelData.key;
            
            // Map provider to expected format for data ingestion
            let providerForIngestion = modelData.provider;
            if (modelData.provider === 'aws_bedrock') {
                providerForIngestion = 'bedrock'; // Expected by data ingestion
            }
            
            return {
                embedding_provider: providerForIngestion, // bedrock, openai, etc.
                embedding_model: modelIdentifier, // actual model ID/name
                embedding_model_key: modelData.key, // UI key (titan_v2, etc.)
                vector_size: modelData.vector_size,
                context_length: modelData.context_length,
                provider_display: modelData.provider_display // for UI display
            };
        }
        
        console.log('⚠️ No embedding model selected');
        return null; // No model selected
    }
    setDefaultModel() {
        console.log('⚠️ Using fallback default model - JSON loading failed!');
        this.availableModels = {
            embeddings: {
                titan_v2: {
                    provider: 'aws_bedrock',
                    model_id: 'amazon.titan-embed-text-v2:0',
                    vector_size: 1536,
                    context_length: 8000,
                    recommended_use: 'general text semantic search, RAG'
                }
            }
        };
        console.log('🔄 Populating dropdown with fallback model...');
        this.populateModelDropdown(this.availableModels.embeddings);
    }
    hasSelectedModel() {
        return this.getSelectedEmbeddingModelPayload() !== null;
    }
    // Debug method to test JSON loading directly
    async testJsonLoad() {
        console.log('🧪 Testing JSON load directly...');
        try {
            const response = await fetch('../models.json');
            console.log('🧪 Response status:', response.status);
            console.log('🧪 Response headers:', [...response.headers.entries()]);
            
            if (response.ok) {
                const text = await response.text();
                console.log('🧪 Raw response text:', text);
                console.log('🧪 Text length:', text.length);
                
                const parsed = JSON.parse(text);
                console.log('🧪 Parsed JSON:', parsed);
                return parsed;
            } else {
                console.error('🧪 Response not OK:', response.statusText);
                return null;
            }
        } catch (error) {
            console.error('🧪 Test failed:', error);
            return null;
        }
    }
}
// Export for use in other modules
window.ModelManager = ModelManager;
// Add global debug function
window.testModelsLoad = async function() {
    console.log('🔍 Starting models load test...');
    const modelManager = new ModelManager();
    const result = await modelManager.testJsonLoad();
    console.log('🔍 Test result:', result);
    return result;
};
