

// ====================================
// API CONFIGURATION
// ====================================
// Detect environment
const BASE_URL =
    window?.API_BASE_URL ||                                  // injected at runtime (e.g. Docker env/proxy)
    (typeof process !== "undefined" && process.env?.API_BASE_URL) || 
    "http://localhost:4000";                                 // default → proxy (recommended for browser)
// If calling Lambda emulator directly, uncomment this:
// const INVOKE_PATH = "/2015-03-31/functions/function/invocations";
// const BASE_URL = "http://localhost:9000" + INVOKE_PATH;
console.log("🌐 API Base URL:", BASE_URL);
// ====================================
// API ENDPOINTS
// ====================================
window.API_ENDPOINTS = {
    GET_PRESIGNED_URL: "/get_presigned_url",
    LIST_PROJECT_FILES: "/list_project_files",
    INGEST_DATA: "/ingest_data",
    RAG_QUERY: "/rag_query",
    RAG_SIMPLE: "/rag_simple",
    GET_MODELS_CONFIG: "/get_models_config",
    UPLOAD_STATUS: "/upload_status",
    DOCUMENT_PREVIEW: "/document_preview",
    BATCH_OPERATIONS: "/batch_operations",
    PROJECT_MANAGEMENT: "/project_management",
    DOCUMENT_SEARCH: "/document_search",
    EXPORT_DATA: "/export_data",
    USER_MANAGEMENT: "/user_management",
    ANALYTICS_DASHBOARD: "/analytics_dashboard",
    NOTIFICATIONS: "/notifications",
    HEALTH: "/health"
};
// ====================================
// API WRAPPER
// ====================================
async function makeApiRequest(endpoint, payload = {}, options = {}) {
    const url = BASE_URL;
    const body = {
        route: endpoint,
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
        const data = await response.json();
        return data;
    } catch (error) {
        console.error(`❌ API request failed: ${endpoint}`, error);
        throw error;
    }
}
// ====================================
// AUTH HELPERS
// ====================================
function getAuthHeaders() {
    const session = getSession();
    if (session?.sessionId) {
        return {
            "X-Session-ID": session.sessionId,
            "X-User-ID": session.user?.username || "anonymous"
        };
    }
    return {};
}
function getSession() {
    try {
        const sessionData = localStorage.getItem("documentBot_session");
        return sessionData ? JSON.parse(sessionData) : null;
    } catch (err) {
        console.error("Error parsing session:", err);
        localStorage.removeItem("documentBot_session");
        return null;
    }
}
// ====================================
// GLOBAL ERROR HANDLING
// ====================================
window.addEventListener("unhandledrejection", e =>
    console.error("Unhandled promise rejection:", e.reason)
);

