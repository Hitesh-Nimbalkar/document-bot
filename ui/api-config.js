// ====================================
// API CONFIGURATION
// ====================================

// Always point to backend (Lambda emulator / API server)
const BASE_URL = "http://localhost:4000";

console.log("🌐 API Base URL:", BASE_URL);

// ====================================
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
            "Content-Type": "application/json",
            ...getAuthHeaders()
        },
        body: JSON.stringify(body),
        ...options
    };

    try {
        console.log(`📡 Request → ${endpoint}`, payload);
        const response = await fetch(url, defaultOptions);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        return await response.json();
    } catch (error) {
        console.error(`❌ API request failed: ${endpoint}`, error);
        throw error;
    }
}
