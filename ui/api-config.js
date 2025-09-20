// ====================================
// API CONFIGURATION FOR DOCUMENT BOT FRONTEND
// ====================================

// Auto-detect environment: if UI served via Docker (hostname != localhost),
// use "lambda:8080". If UI opened in host browser, use "localhost:9000".
const isDockerEnv = window.location.hostname !== "localhost";

const API_CONFIG = {
    BASE_URL: isDockerEnv
        ? "http://lambda:8080/2015-03-31/functions/function/invocations"   // UI container → Lambda
        : "http://localhost:9000/2015-03-31/functions/function/invocations" // Browser → Lambda
};

// ====================================
// API ENDPOINTS - Routes are passed in body, not appended to URL
// ====================================
const API_ENDPOINTS = {
    USER_MANAGEMENT: "/user_management",
    GET_PRESIGNED_URL: "/get_presigned_url",
    INGEST_DATA: "/ingest_data",
    LIST_PROJECT_FILES: "/list_project_files",
    RAG_QUERY: "/rag_query",
    GET_MODELS_CONFIG: "/get_models_config",
    UPLOAD_STATUS: "/upload_status",
    DOCUMENT_PREVIEW: "/document_preview",
    BATCH_OPERATIONS: "/batch_operations",
    PROJECT_MANAGEMENT: "/project_management",
    DOCUMENT_SEARCH: "/document_search",
    EXPORT_DATA: "/export_data",
    ANALYTICS_DASHBOARD: "/analytics_dashboard",
    NOTIFICATIONS: "/notifications",
    HEALTH: "/health",
    ROUTES: "/routes"
};

// ====================================
// API UTILITY FUNCTIONS
// ====================================

/**
 * Always return the Lambda invocation URL
 */
function buildApiUrl() {
    return API_CONFIG.BASE_URL;
}

/**
 * Simplified API request wrapper
 * Automatically wraps payload in { route, payload }
 */
async function makeApiRequest(endpoint, payload = {}, options = {}) {
    const url = buildApiUrl();

    const requestBody = {
        route: endpoint,
        payload: payload
    };

    const defaultOptions = {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            ...getAuthHeaders()
        },
        body: JSON.stringify(requestBody),
        ...options
    };

    try {
        console.log(`📡 API Request → ${url}`, requestBody);

        const response = await fetch(url, defaultOptions);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        console.log("✅ API Response:", data);
        return data;

    } catch (error) {
        console.error("❌ API Request failed:", error);
        throw error;
    }
}

// ====================================
// AUTH & SESSION HELPERS
// ====================================
function getAuthHeaders() {
    const session = getSession();
    if (session && session.sessionId) {
        return {
            "X-Session-ID": session.sessionId,
            "X-User-ID": session.user ? session.user.username : "anonymous"
        };
    }
    return {};
}

function getSession() {
    try {
        const sessionData = localStorage.getItem("documentBot_session");
        if (sessionData) {
            return JSON.parse(sessionData);
        }
    } catch (error) {
        console.error("Error reading session:", error);
        localStorage.removeItem("documentBot_session");
    }
    return null;
}

function generateSessionId() {
    const timestamp = Date.now().toString(36);
    const randomPart = Math.random().toString(36).substring(2, 15);
    return `session_${timestamp}_${randomPart}`;
}

function saveSession(userData) {
    try {
        const sessionData = {
            ...userData,
            sessionId: generateSessionId(),
            loginTime: Date.now()
        };
        localStorage.setItem("documentBot_session", JSON.stringify(sessionData));
        console.log("Session created with ID:", sessionData.sessionId);
    } catch (error) {
        console.error("Error saving session:", error);
    }
}

function getSessionId() {
    const session = getSession();
    return session ? session.sessionId : null;
}

function logout() {
    const session = getSession();
    if (session && session.sessionId) {
        console.log("Logging out session:", session.sessionId);
    }
    localStorage.removeItem("documentBot_session");
    window.location.href = "index.html";
}

function requireAuth() {
    const session = getSession();
    if (!session || !session.isLoggedIn) {
        window.location.href = "login.html";
        return null;
    }
    return session;
}

// ====================================
// ERROR HANDLING
// ====================================
window.addEventListener("unhandledrejection", function(event) {
    console.error("Unhandled promise rejection:", event.reason);
});
