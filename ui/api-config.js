// ====================================
// API CONFIGURATION
// ====================================
// const BASE_URL =
//     window?.API_BASE_URL ||                       // runtime-injected
//     (typeof process !== "undefined" && process.env?.API_BASE_URL) || // Node
//     "http://localhost:4000";                      // fallback

// Set API Gateway endpoint as BASE_URL
const BASE_URL =
    window?.API_BASE_URL ||                       // runtime-injected
    (typeof process !== "undefined" && process.env?.API_BASE_URL) ||
    "https://o7mffihfkj.execute-api.ap-south-1.amazonaws.com/dev/bot;  


window.API_ENDPOINTS = {
    GET_PRESIGNED_URL: "/get_presigned_url",
    INGEST_DATA: "/ingest_data",
    RAG_QUERY: "/rag_query",
    RAG_SIMPLE: "/rag_simple",
    HEALTH: "/health"
};

// ====================================
// SESSION MANAGEMENT
// ====================================
window.SessionManager = {
    getSessionId() {
        // First check plain keys
        let id =
            localStorage.getItem('session_id') ||
            sessionStorage.getItem('session_id') ||
            localStorage.getItem('user_session_id');

        if (!id) {
            // Fallback: look inside the JSON blob used by login page
            const raw = localStorage.getItem('documentBot_session');
            if (raw) {
                try {
                    const parsed = JSON.parse(raw);
                    if (parsed.sessionId) {
                        id = parsed.sessionId;
                        // 👉 store it under simple keys for other pages
                        localStorage.setItem('session_id', id);
                        sessionStorage.setItem('session_id', id);
                    }
                } catch (err) {
                    console.warn('⚠️ Could not parse documentBot_session', err);
                }
            }
        }

        // Still nothing? Generate a new one
        if (!id) {
            id = this.generateSessionId();
        }

        return id;
    },

    setSessionId(sessionId) {
        localStorage.setItem('session_id', sessionId);
        sessionStorage.setItem('session_id', sessionId);
        // also patch the blob if it exists
        const blob = localStorage.getItem('documentBot_session');
        if (blob) {
            try {
                const parsed = JSON.parse(blob);
                parsed.sessionId = sessionId;
                parsed.isLoggedIn = true;
                localStorage.setItem('documentBot_session', JSON.stringify(parsed));
            } catch (err) {
                console.warn('⚠️ Could not update documentBot_session', err);
            }
        }
        window.dispatchEvent(new CustomEvent('sessionUpdated', { detail: { sessionId } }));
        console.log('✅ Session ID set:', sessionId);
    },

    generateSessionId() {
        const sessionId = 'sess_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
        this.setSessionId(sessionId);
        return sessionId;
    },

    clearSession() {
        localStorage.removeItem('session_id');
        sessionStorage.removeItem('session_id');
        localStorage.removeItem('user_session_id');
        // optional: also clear main blob
        localStorage.removeItem('documentBot_session');
        window.dispatchEvent(new CustomEvent('sessionCleared'));
        console.log('🗑️ Session cleared');
    }
};

// ====================================
// AUTH HEADERS HELPER
// ====================================
function getAuthHeaders() {
    const sessionId = window.SessionManager.getSessionId();
    const headers = { 'Content-Type': 'application/json' };
    if (sessionId) headers['X-Session-ID'] = sessionId;
    return headers;
}

// ====================================
// API WRAPPER
// ====================================
async function makeApiRequest(endpoint, payload = {}, options = {}) {
    const url = BASE_URL;
    const body = { route: endpoint, payload };
    const defaultOptions = {
        method: "POST",
        headers: { ...getAuthHeaders(), ...options.headers },
        body: JSON.stringify(body),
        ...options
    };
    try {
        console.log(`📡 Request → ${endpoint}`, payload);
        const response = await fetch(url, defaultOptions);
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`HTTP ${response.status}: ${response.statusText} - ${errorText}`);
        }
        return await response.json();
    } catch (error) {
        console.error(`❌ API request failed: ${endpoint}`, error);
        throw error;
    }
}

// Make functions globally available
window.makeApiRequest = makeApiRequest;
window.getAuthHeaders = getAuthHeaders;

// ====================================
// INITIALIZE SESSION ON LOAD
// ====================================
document.addEventListener('DOMContentLoaded', () => {
    const sessionId = window.SessionManager.getSessionId();
    console.log('🎯 Session initialized:', sessionId);
});
console.log('✅ API Config loaded successfully');
