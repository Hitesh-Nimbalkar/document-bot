

// ====================================
// API CONFIGURATION
// ====================================
// Always point to backend (Lambda emulator / API server)
const BASE_URL =
    window?.API_BASE_URL ||                       // if injected at runtime (browser env)
    (typeof process !== "undefined" && process.env?.API_BASE_URL) || // if running in Node
    "http://localhost:4000";                      // fallback default

// API ENDPOINTS
// ====================================
window.API_ENDPOINTS = {
    GET_PRESIGNED_URL: "/get_presigned_url",
    INGEST_DATA: "/ingest_data",
    RAG_QUERY: "/rag_query",
    RAG_SIMPLE: "/rag_simple",
    HEALTH: "/health"
};
// ====================================
// AUTH HEADERS HELPER
// ====================================
function getAuthHeaders() {
    const sessionId = localStorage.getItem('session_id') || 
                     sessionStorage.getItem('session_id') || 
                     localStorage.getItem('user_session_id');
    
    const headers = {
        'Content-Type': 'application/json'
    };
    
    if (sessionId) {
        headers['X-Session-ID'] = sessionId;
    }
    
    return headers;
}
// ====================================
// API WRAPPER
// ====================================
async function makeApiRequest(endpoint, payload = {}, options = {}) {
    const url = BASE_URL;   // always backend
    const body = {
        route: endpoint,    // Lambda expects "route"
        payload
    };
    const defaultOptions = {
        method: "POST",
        headers: {
            ...getAuthHeaders(),
            ...options.headers
        },
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
console.log('✅ API Config loaded successfully');

