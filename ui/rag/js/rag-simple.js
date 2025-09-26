// ==================================================
// 🚀 RAG CHAT INTERFACE - MAIN ENTRY
// ==================================================
document.addEventListener('DOMContentLoaded', () => {
    console.log('🚀 Initializing RAG Chat interface');
    new RAGChatInterface();
    loadUserSession();
});

// ==================================================
// 🧠 RAG CHAT INTERFACE CLASS (Core Logic)
// ==================================================
class RAGChatInterface {
    constructor() {
        this.chatContainer = document.getElementById('chatContainer');
        this.chatForm = document.getElementById('chatForm');
        this.chatQuery = document.getElementById('chatQuery');
        this.sendBtn = document.getElementById('sendBtn');
        this.clearChatBtn = document.getElementById('clearChatBtn');

        this.initializeEventListeners();
        this.loadModels();
    }

    initializeEventListeners() {
        this.chatForm.addEventListener('submit', e => {
            e.preventDefault();
            this.handleChatSubmit();
        });
        this.clearChatBtn.addEventListener('click', () => this.clearChatHistory());
        this.chatQuery.addEventListener('input', () => this.autoResizeTextarea());
        this.chatQuery.addEventListener('keypress', e => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.handleChatSubmit();
            }
        });
    }

    async loadModels() {
        try {
            if (typeof loadAvailableModels === 'function') {
                await loadAvailableModels();
            } else {
                console.warn('⚠️ Model loading function not available');
            }
        } catch (error) {
            console.error('Failed to load models:', error);
            this.addErrorMessage('Failed to load available models. Please refresh the page.');
        }
    }

    validateConfiguration() {
        const projectName = document.getElementById('projectName').value.trim();
        const llmModel = document.getElementById('llmModel').value;
        const embeddingModel = document.getElementById('embeddingModel').value;
        if (!projectName) throw new Error('Please enter a project name');
        if (!llmModel) throw new Error('Please select an AI model');
        if (!embeddingModel) throw new Error('Please select an embedding model');
        return { projectName, llmModel, embeddingModel };
    }

    async handleChatSubmit() {
        const query = this.chatQuery.value.trim();
        if (!query) return;
        try {
            const config = this.validateConfiguration();
            this.addUserMessage(query);
            this.chatQuery.value = '';
            this.autoResizeTextarea();
            this.setLoading(true);
            const loadingId = this.addLoadingMessage();
            const formData = await this.collectFormData(query, config);
            const response = await makeRagSimpleQuery(formData);
            this.removeMessage(loadingId);
            this.addAIResponse(response);
        } catch (error) {
            console.error('Chat error:', error);
            this.removeLoadingMessage();
            this.addErrorMessage(error.message || 'Error processing request');
        } finally {
            this.setLoading(false);
        }
    }

    async collectFormData(query, config) {
        // 🔹 Directly fetch from localStorage
        let sessionId = null;
        const raw = localStorage.getItem('documentBot_session');
        if (raw) {
            try {
                const parsed = JSON.parse(raw);
                if (parsed.sessionId) {
                    sessionId = parsed.sessionId;
                    // also set simple keys
                    localStorage.setItem('session_id', sessionId);
                    sessionStorage.setItem('session_id', sessionId);
                }
            } catch (err) {
                console.warn('⚠️ Failed to parse documentBot_session', err);
            }
        }

        if (!sessionId) {
            sessionId = localStorage.getItem('session_id') ||
                        sessionStorage.getItem('session_id');
        }

        if (!sessionId) throw new Error('Session ID is required. Please log in first.');

        let userId = `user_${Date.now()}`;
        let userRole = 'customer';
        if (raw) {
            try {
                const parsed = JSON.parse(raw);
                if (parsed.user?.userId) userId = parsed.user.userId;
                if (parsed.user?.role) userRole = parsed.user.role;
            } catch {}
        }

        const defaults = window.modelManager
            ? (await window.modelManager.getConfig()).default_configuration || {}
            : {};

        return {
            project_name: config.projectName,
            user_id: userId,
            session_id: sessionId,
            query,
            metadata: {
                llm_model: config.llmModel,
                embedding_model: config.embeddingModel,
                bedrock_region: defaults.bedrock_region || 'ap-south-1',
                temperature: parseFloat(document.getElementById('temperature').value),
                max_tokens: parseInt(document.getElementById('maxTokens').value),
                top_k: defaults.top_k || 3,
                user_role: userRole
            }
        };
    }

    addUserMessage(msg) { this.#appendMessage('user', msg); }

    addAIResponse(response) {
        const messageId = this.#createMsgId();
        let data = response?.body
            ? (typeof response.body === 'string' ? JSON.parse(response.body) : response.body)
            : response;
        const answer = data.answer?.summary || 'No response received';
        const metadata = data.metadata || data;

        const messageElement = document.createElement('div');
        messageElement.className = 'chat-message ai-message';
        messageElement.id = messageId;

        let html = `
            <div class="message-avatar"><i class="fas fa-robot"></i></div>
            <div class="message-content">
                <div class="message-text answer-text">
                    ${this.#formatResponse(answer)}
                </div>
        `;

        const metaPieces = [];
        if (metadata?.performance?.total_time) {
            metaPieces.push(`<span class="meta-item"><i class="fas fa-clock me-1"></i>${metadata.performance.total_time}s</span>`);
        }
        if (metadata?.detected_intent) {
            metaPieces.push(`<span class="meta-item"><i class="fas fa-bullseye me-1"></i>${this.#escape(metadata.detected_intent)}</span>`);
        }
        if (metadata?.sources?.length) {
            const src = metadata.sources.slice(0, 3).map(s => `
                <div class="source-doc">
                    <span class="source-title">${this.#escape(s.filename || s.title || 'Document')}</span>
                    <span class="source-score">${(s.score * 100).toFixed(1)}%</span>
                </div>`).join('');
            metaPieces.push(`<div class="source-block"><small class="text-muted"><i class="fas fa-book-open me-1"></i>Sources:</small>${src}</div>`);
        }
        if (metaPieces.length) html += `<div class="meta-info">${metaPieces.join('')}</div>`;
        html += `<div class="message-time">${this.#time()}</div></div>`;
        messageElement.innerHTML = html;

        this.chatContainer.appendChild(messageElement);
        this.scrollToBottom();
    }

    addLoadingMessage() {
        const id = this.#createMsgId();
        const el = document.createElement('div');
        el.className = 'chat-message ai-message loading-message';
        el.id = id;
        el.innerHTML = `
            <div class="message-avatar"><i class="fas fa-robot"></i></div>
            <div class="message-content">
                <span>AI is thinking</span>
                <div class="typing-indicator">
                    <div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>
                </div>
            </div>`;
        this.chatContainer.appendChild(el);
        this.scrollToBottom();
        return id;
    }

    addErrorMessage(msg) { this.#appendMessage('error', msg); }

    removeMessage(id) { const el = document.getElementById(id); if (el) el.remove(); }
    removeLoadingMessage() { this.chatContainer.querySelector('.loading-message')?.remove(); }
    clearChatHistory() { [...this.chatContainer.querySelectorAll('.chat-message:not(:first-child)')].forEach(m => m.remove()); }

    setLoading(isLoading) {
        this.sendBtn.disabled = isLoading;
        this.chatQuery.disabled = isLoading;
        this.sendBtn.innerHTML = isLoading
            ? '<i class="fas fa-spinner fa-spin"></i>'
            : '<i class="fas fa-paper-plane"></i>';
    }

    autoResizeTextarea() {
        this.chatQuery.style.height = 'auto';
        this.chatQuery.style.height = Math.min(this.chatQuery.scrollHeight, 120) + 'px';
    }

    scrollToBottom() {
        setTimeout(() => this.chatContainer.scrollTop = this.chatContainer.scrollHeight, 100);
    }

    #appendMessage(type, msg) {
        const id = this.#createMsgId();
        const el = document.createElement('div');
        el.className = `chat-message ${type}-message`;
        el.id = id;
        el.innerHTML = `
            <div class="message-avatar">${type === 'user' ? '<i class="fas fa-user"></i>' : '<i class="fas fa-robot"></i>'}</div>
            <div class="message-content">
                <div class="message-text">${this.#escape(msg)}</div>
                <div class="message-time">${this.#time()}</div>
            </div>`;
        this.chatContainer.appendChild(el);
        this.scrollToBottom();
    }

    #createMsgId() { return `msg_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`; }
    #time() { return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); }
    #escape(txt) { const d = document.createElement('div'); d.textContent = txt; return d.innerHTML; }
    #formatResponse(text) {
        return text.replace(/\n\n/g, '</p><p>').replace(/\n/g, '<br>').replace(/^/, '<p>').replace(/$/, '</p>');
    }
}

// ==================================================
// 🔧 SHARED UTILITIES
// ==================================================
async function makeRagSimpleQuery(payload) {
    if (typeof makeApiRequest === 'function' && window.API_ENDPOINTS) {
        return makeApiRequest(window.API_ENDPOINTS.RAG_SIMPLE, payload);
    } else {
        throw new Error('API configuration not available. Please ensure api-config.js is loaded.');
    }
}

function loadUserSession() {
    let sessionId = null;
    const raw = localStorage.getItem('documentBot_session');
    if (raw) {
        try {
            const parsed = JSON.parse(raw);
            if (parsed.sessionId) {
                sessionId = parsed.sessionId;
                localStorage.setItem('session_id', sessionId);
                sessionStorage.setItem('session_id', sessionId);
            }
        } catch {}
    }

    if (!sessionId) {
        sessionId = localStorage.getItem('session_id') ||
                    sessionStorage.getItem('session_id');
    }

    const warningArea = document.getElementById('sessionWarning');
    if (!sessionId) {
        console.warn('⚠️ No session ID found - user must log in');
        if (warningArea) {
            warningArea.innerHTML =
                '<div class="alert alert-warning"><i class="fas fa-exclamation-triangle me-1"></i>Please log in to use RAG</div>';
            warningArea.style.display = 'block';
        }
    } else {
        if (warningArea) warningArea.style.display = 'none';
        if (raw) {
            try {
                const parsed = JSON.parse(raw);
                const username = parsed.user?.username;
                const userElement = document.getElementById('currentUser');
                if (username && userElement) userElement.textContent = username;
            } catch {}
        }
        console.log('✅ Session loaded for RAG:', sessionId);
    }
}

function getAuthToken() {
    return localStorage.getItem('authToken') || sessionStorage.getItem('authToken') || '';
}

console.log('✅ RAG Simple loaded - Using ModelManager');
