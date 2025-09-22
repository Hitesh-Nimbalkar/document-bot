

class ModelManager {
    static instance = null;
    
    constructor() {
        if (ModelManager.instance) {
            return ModelManager.instance;
        }
        
        this.config = null;
        this.loading = null;
        ModelManager.instance = this;
    }
    
    async getConfig() {
        if (this.config) return this.config;
        
        if (!this.loading) {
            this.loading = fetch('models.json').then(r => r.json());
        }
        
        this.config = await this.loading;
        return this.config;
    }
    
    async getLLMModels() {
        const config = await this.getConfig();
        return config.llm_models || [];
    }
    
    async getEmbeddingModels() {
        const config = await this.getConfig();
        return config.embedding_models || [];
    }
    
    async populateSelect(selectId, models, getDisplayName) {
        const select = document.getElementById(selectId);
        if (!select) return;
        
        select.innerHTML = '';
        models.forEach(model => {
            const option = new Option(getDisplayName(model), model.id, false, model.recommended);
            select.appendChild(option);
        });
    }
    
    async initializeUI() {
        const [llmModels, embeddingModels, defaults] = await Promise.all([
            this.getLLMModels(),
            this.getEmbeddingModels(),
            this.getConfig().then(c => c.default_configuration || {})
        ]);
        
        // Populate dropdowns
        await this.populateSelect('llmModel', llmModels, 
            model => model.recommended ? `🚀 ${model.name} (Recommended)` : model.name);
        
        await this.populateSelect('embeddingModel', embeddingModels,
            model => model.recommended ? `🔥 ${model.name} (Latest)` : `📚 ${model.name}`);
        
        // Apply defaults
        Object.entries(defaults).forEach(([key, value]) => {
            const element = document.getElementById(key);
            if (element) element.value = value;
        });
    }
}
// Global singleton
window.modelManager = new ModelManager();
// Auto-initialize
document.addEventListener('DOMContentLoaded', () => {
    window.modelManager.initializeUI();
});
