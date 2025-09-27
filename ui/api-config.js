// ====================================
// API CONFIGURATION
// ====================================

// ✅ Choose the correct API base URL
const BASE_URL =
    window?.API_BASE_URL ||                       // runtime-injected
    (typeof process !== "undefined" && process.env?.API_BASE_URL) ||
    "https://j6ufq5gja9.execute-api.ap-south-1.amazonaws.com/dev/bot"; // fallback if nothing injected

// ✅ Central list of all API endpoints
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

// Always pull the session id from the real SessionManager instance
function getAuthHeaders() {
    const sessionId = window.sessionManager?.getSessionId?.();
    const headers = { 'Content-Type': 'application/json' };
    if (sessionId) headers['X-Session-ID'] = sessionId;
    return headers;
}

// ====================================
// API WRAPPER
// ====================================

// Main helper for making API calls
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

// Expose globally
window.makeApiRequest = makeApiRequest;
window.getAuthHeaders = getAuthHeaders;

console.log('✅ API Config loaded successfully');
