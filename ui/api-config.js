
// API Configuration for Document Bot Frontend
// This file contains the common API Gateway base URL and utility functions
// ====================================
// ENVIRONMENT CONFIGURATION
// ====================================
// API Gateway Base URL - Update this with your actual API Gateway URL
const API_CONFIG = {
    BASE_URL: "http://localhost:9000/2015-03-31/functions/function/invocations"
};
// ====================================
// API ENDPOINTS - All Lambda routes
// ====================================
const API_ENDPOINTS = {
    // Authentication
    USER_MANAGEMENT: '/user_management',
    
    // Core Document Operations  
    GET_PRESIGNED_URL: '/get_presigned_url',
    DATA_INGESTION: '/data_ingestion',
    INGEST_DATA: '/ingest_data',
    LIST_PROJECT_FILES: '/list_project_files',
    RAG_QUERY: '/rag_query',
    GET_MODELS_CONFIG: '/get_models_config',
    
    // UI Operations
    UPLOAD_STATUS: '/upload_status',
    DOCUMENT_PREVIEW: '/document_preview', 
    BATCH_OPERATIONS: '/batch_operations',
    PROJECT_MANAGEMENT: '/project_management',
    DOCUMENT_SEARCH: '/document_search',
    EXPORT_DATA: '/export_data',
    ANALYTICS_DASHBOARD: '/analytics_dashboard',
    NOTIFICATIONS: '/notifications',
    
    // Health & Info
    HEALTH: '/health',
    ROUTES: '/routes'
};
// ====================================
// API UTILITY FUNCTIONS
// ====================================
/**
 * Build complete API URL
 * @param {string} endpoint - Endpoint path from API_ENDPOINTS
 * @returns {string} Complete API URL
 */
function buildApiUrl(endpoint) {
    return `${API_CONFIG.BASE_URL}${endpoint}`;
}
// ====================================
// SIMPLIFIED API FUNCTIONS FOR DUMMY LOGIN
// ====================================
/**
 * Simple API request function (no complex retry logic for now)
 * @param {string} endpoint - API endpoint
 * @param {Object} options - Fetch options
 * @returns {Promise<Object>} API response
 */
async function makeApiRequest(endpoint, options = {}) {
    const url = buildApiUrl(endpoint);
    
    const defaultOptions = {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...getAuthHeaders()
        },
        ...options
    };
    try {
        console.log(`API Request: ${options.method || 'POST'} ${url}`);
        
        const response = await fetch(url, defaultOptions);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        console.log(`API Response: Success`, data);
        return data;
        
    } catch (error) {
        console.error(`API Request failed:`, error);
        throw error;
    }
}
/**
 * Get authentication headers from stored session
 * @returns {Object} Headers object with session info
 */
function getAuthHeaders() {
    const session = getSession();
    if (session && session.sessionId) {
        return {
            'X-Session-ID': session.sessionId,
            'X-User-ID': session.user ? session.user.username : 'anonymous'
        };
    }
    return {};
}
/**
 * Get current user session from localStorage
 * @returns {Object|null} Session data or null
 */
function getSession() {
    try {
        const sessionData = localStorage.getItem('documentBot_session');
        if (sessionData) {
            const session = JSON.parse(sessionData);
            return session; // Return session without expiry checks for dummy login
        }
    } catch (error) {
        console.error('Error reading session:', error);
        localStorage.removeItem('documentBot_session');
    }
    return null;
}
// ====================================
// SESSION ID GENERATION AND MANAGEMENT
// ====================================
/**
 * Generate a unique session ID
 * @returns {string} Unique session ID
 */
function generateSessionId() {
    // Generate a UUID-like session ID
    const timestamp = Date.now().toString(36);
    const randomPart = Math.random().toString(36).substring(2, 15);
    return `session_${timestamp}_${randomPart}`;
}
/**
 * Save user session to localStorage with session ID
 * @param {Object} userData - User data to save
 */
function saveSession(userData) {
    try {
        const sessionData = {
            ...userData,
            sessionId: generateSessionId(), // Generate unique session ID
            loginTime: Date.now()
        };
        localStorage.setItem('documentBot_session', JSON.stringify(sessionData));
        console.log('Session created with ID:', sessionData.sessionId);
    } catch (error) {
        console.error('Error saving session:', error);
    }
}
/**
 * Get current session ID
 * @returns {string|null} Session ID if logged in
 */
function getSessionId() {
    const session = getSession();
    return session ? session.sessionId : null;
}
/**
 * Clear user session and redirect to login
 */
function logout() {
    const session = getSession();
    if (session && session.sessionId) {
        console.log('Logging out session:', session.sessionId);
    }
    localStorage.removeItem('documentBot_session');
    window.location.href = 'index.html';
}
/**
 * Check if user is logged in (simple check for dummy login)
 * @returns {Object|null} Session data if logged in
 */
function requireAuth() {
    const session = getSession();
    if (!session || !session.isLoggedIn) {
        // Redirect to login if not logged in
        window.location.href = 'login.html';
        return null;
    }
    return session;
}
// ====================================
// SESSION ID ONLY - NO OTHER API FUNCTIONS
// ====================================
// Session ID is generated and stored. 
// API functions will be added later when needed.
// ====================================
// SIMPLIFIED ERROR HANDLING
// ====================================
window.addEventListener('unhandledrejection', function(event) {
    console.error('Unhandled promise rejection:', event.reason);
});
// ====================================
// EXPORT FOR MODULES (if using ES6 modules)
// ====================================
// For ES6 modules, uncomment these:
// export { API_CONFIG, API_ENDPOINTS, makeApiRequest, authenticateUser, getPresignedUrl, submitRagQuery, requireAuth, logout };
