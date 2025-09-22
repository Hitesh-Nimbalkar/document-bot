// ====================================
// RAG SIMPLE QUERY INTERFACE
// ====================================

document.addEventListener('DOMContentLoaded', async function() {
    await initializeRagSimple();
});

async function initializeRagSimple() {
    console.log('🚀 Initializing RAG Simple interface');
    
    // Setup form submission
    const form = document.getElementById('ragSimpleForm');
    if (form) {
        form.addEventListener('submit', handleFormSubmit);
    }
    
    // Models are already handled by ModelManager
    loadUserSession();
}

async function handleFormSubmit(event) {
    event.preventDefault();
    
    const submitBtn = document.getElementById('submitBtn');
    const originalBtnText = submitBtn.innerHTML;
    
    try {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Querying...';
        
        showLoadingState();
        
        const formData = await collectFormData();
        
        // Validate required fields
        if (!formData.query || !formData.project_name || !formData.llm_model || !formData.embedding_model) {
            throw new Error('Please fill in all required fields');
        }
        
        console.log('📤 Sending RAG query:', formData);
        
        const response = await makeRagSimpleQuery(formData);
        displayResults(response);
        
    } catch (error) {
        console.error('❌ RAG query failed:', error);
        showError(error.message || 'Query failed');
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = originalBtnText;
    }
}

async function collectFormData() {
    const sessionId = localStorage.getItem('session_id') || 
                     sessionStorage.getItem('session_id') || 
                     localStorage.getItem('user_session_id');
    
    if (!sessionId) {
        throw new Error('Session ID is required. Please log in first.');
    }
    
    // Get default config from ModelManager instead of duplicating
    const config = await window.modelManager.getConfig();
    const defaults = config.default_configuration || {};
    
    return {
        query: document.getElementById('query').value.trim(),
        project_name: document.getElementById('projectName').value.trim(),
        llm_model: document.getElementById('llmModel').value,
        embedding_model: document.getElementById('embeddingModel').value,
        bedrock_region: defaults.bedrock_region || 'ap-south-1',
        temperature: parseFloat(document.getElementById('temperature').value),
        max_tokens: parseInt(document.getElementById('maxTokens').value),
        top_k: defaults.top_k || 3,
        session_id: sessionId
    };
}

// ✅ Use shared API wrapper from api-config.js
async function makeRagSimpleQuery(payload) {
    return makeApiRequest(window.API_ENDPOINTS.RAG_SIMPLE, payload);
}

function showLoadingState() {
    document.getElementById('loadingSpinner').style.display = 'block';
    document.getElementById('resultsContent').style.display = 'none';
    document.getElementById('errorMessage').style.display = 'none';
    const placeholderState = document.getElementById('placeholderState');
    if (placeholderState) placeholderState.style.display = 'none';
}

function displayResults(response) {
    document.getElementById('loadingSpinner').style.display = 'none';
    document.getElementById('resultsContent').style.display = 'block';
    document.getElementById('errorMessage').style.display = 'none';
    
    let data = response;
    if (typeof response.body === 'string') {
        data = JSON.parse(response.body);
    } else if (response.body) {
        data = response.body;
    }

    // ✅ Show answer
    const answerSummary = data.answer && data.answer.summary 
        ? data.answer.summary 
        : 'No answer provided';
    document.getElementById('answerText').innerHTML = answerSummary;

    // ✅ Show query details
    if (document.getElementById('originalQuery')) {
        document.getElementById('originalQuery').textContent = data.query || '';
    }
    if (document.getElementById('cleanedQuery')) {
        document.getElementById('cleanedQuery').textContent = data.clean_query || '';
    }
    if (document.getElementById('detectedIntent')) {
        document.getElementById('detectedIntent').textContent = data.detected_intent || 'UNKNOWN';
    }
    if (document.getElementById('pipelineMode')) {
        document.getElementById('pipelineMode').textContent = data.pipeline_mode || '';
    }

    // ✅ Show metrics
    const perf = data.performance || {};
    document.getElementById('processingTime').textContent = 
        perf.total_time ? `${perf.total_time}s` : 'N/A';
    document.getElementById('documentsFound').textContent = 
        data.total_sources || 0;
    if (document.getElementById('intentTime')) {
        document.getElementById('intentTime').textContent = perf.intent_detection_time || '0';
    }
    if (document.getElementById('embeddingTime')) {
        document.getElementById('embeddingTime').textContent = perf.embedding_time || '0';
    }
    if (document.getElementById('searchTime')) {
        document.getElementById('searchTime').textContent = perf.search_time || '0';
    }
    if (document.getElementById('contextTime')) {
        document.getElementById('contextTime').textContent = perf.context_time || '0';
    }
    if (document.getElementById('generationTime')) {
        document.getElementById('generationTime').textContent = perf.generation_time || '0';
    }
    if (document.getElementById('perfBreakdown')) {
        document.getElementById('perfBreakdown').textContent = perf.breakdown || '';
    }
    document.getElementById('metricsRow').style.display = 'block';

    // ✅ Show cost
    if (data.cost_usd && document.getElementById('costInfo')) {
        document.getElementById('costInfo').textContent = `$${data.cost_usd.toFixed(4)}`;
        document.getElementById('costRow').style.display = 'block';
    } else if (document.getElementById('costRow')) {
        document.getElementById('costRow').style.display = 'none';
    }

    // ✅ Show sources
    const sources = data.sources || [];
    if (sources.length > 0) {
        document.getElementById('sourceDocuments').innerHTML = formatSources(sources);
        document.getElementById('sourceSection').style.display = 'block';
    } else {
        document.getElementById('sourceSection').style.display = 'none';
    }
}

function formatSources(sources) {
    return sources.map((source, index) => {
        const fileName = source.filename || `Document ${index + 1}`;
        const content = source.content || 'No content';
        const score = source.score ? `(${Math.round(source.score * 100)}%)` : '';
        
        return `
            <div class="source-doc-card mb-3">
                <h6><i class="fas fa-file-alt me-2"></i>${fileName} ${score}</h6>
                <p class="text-muted">${content.substring(0, 200)}...</p>
            </div>
        `;
    }).join('');
}

function showError(message) {
    document.getElementById('loadingSpinner').style.display = 'none';
    document.getElementById('resultsContent').style.display = 'none';
    document.getElementById('errorMessage').style.display = 'block';
    const placeholderState = document.getElementById('placeholderState');
    if (placeholderState) placeholderState.style.display = 'none';
    document.getElementById('errorText').textContent = message;
}

function loadUserSession() {
    const sessionId = localStorage.getItem('session_id') || 
                     sessionStorage.getItem('session_id') || 
                     localStorage.getItem('user_session_id');
    
    if (!sessionId) {
        console.warn('⚠️ No session ID found - user must log in');
        const warningArea = document.getElementById('sessionWarning');
        if (warningArea) {
            warningArea.innerHTML = '<div class="alert alert-warning"><i class="fas fa-exclamation-triangle me-1"></i>Please log in to use RAG functionality</div>';
            warningArea.style.display = 'block';
        }
    } else {
        console.log('✅ Session ID found - user authenticated');
        const warningArea = document.getElementById('sessionWarning');
        if (warningArea) {
            warningArea.style.display = 'none';
        }
    }
}

function logout() {
    try {
        if (typeof window.logout === 'function') {
            window.logout();
        } else {
            localStorage.clear();
            sessionStorage.clear();
            window.location.href = '../index.html';
        }
    } catch (error) {
        console.error('❌ Logout error:', error);
        window.location.href = '../index.html';
    }
}

console.log('✅ RAG Simple loaded - Using ModelManager');
