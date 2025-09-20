
/**
 * Session Management Module
 * Handles user session state and authentication
 */
class SessionManager {
    constructor() {
        this.currentSession = null;
        this.initializeSession();
    }
    initializeSession() {
        // Load session using the same method as dashboard (for compatibility)
        this.currentSession = this.getSession();
        if (this.currentSession) {
            console.log('📱 Session restored:', this.currentSession.user?.username);
        } else {
            console.log('🔓 No valid session found');
        }
    }
    getSession() {
        try {
            // Use the same localStorage key as the dashboard
            const sessionData = localStorage.getItem('documentBot_session');
            if (!sessionData) return null;
            
            const session = JSON.parse(sessionData);
            
            // Check if session is expired
            if (session.expiresAt && new Date() > new Date(session.expiresAt)) {
                console.warn('Session expired');
                this.clearSession();
                return null;
            }
            
            return session;
        } catch (error) {
            console.error('Error reading session:', error);
            return null;
        }
    }
    updateUserDisplay() {
        const userDisplay = document.getElementById('userDisplay');
        if (userDisplay && this.currentSession?.user) {
            userDisplay.textContent = `Welcome, ${this.currentSession.user.username}`;
        }
    }
    clearSession() {
        localStorage.removeItem('documentBot_session');
        localStorage.removeItem('documentBotSession'); // Clear both formats
        this.currentSession = null;
    }
    logout() {
        if (confirm('Are you sure you want to logout?')) {
            this.clearSession();
            window.location.href = '../login.html';
        }
    }
    isValidSession() {
        return this.currentSession && 
               this.currentSession.sessionId && 
               this.currentSession.user &&
               this.currentSession.isLoggedIn === true; // Check for dashboard compatibility
    }
    async validateSession() {
        try {
            // For now, just do local validation to avoid blocking the UI
            // In a real app, you would validate with the server here
            const isValid = this.isValidSession();
            console.log('✅ Session validation result:', isValid);
            
            if (isValid) {
                console.log('✅ Session validated successfully (local check)');
                return true;
            } else {
                console.log('❌ No valid session found in storage');
                return false;
            }
        } catch (error) {
            console.error('❌ Session validation error:', error);
            // If validation fails, still allow local session if it exists
            return this.isValidSession();
        }
    }
    getAuthHeaders() {
        if (!this.isValidSession()) {
            return {};
        }
        return {
            'Authorization': `Bearer ${this.currentSession.sessionId}`,
            'X-Session-ID': this.currentSession.sessionId,
            'X-User-ID': this.currentSession.user ? this.currentSession.user.username : 'anonymous'
        };
    }
    updateUserInfo() {
        const userInfoElement = document.getElementById('userInfo');
        if (userInfoElement && this.isValidSession()) {
            const username = this.currentSession.user.username || 'Unknown User';
            userInfoElement.textContent = `Welcome, ${username}`;
        } else if (userInfoElement) {
            userInfoElement.textContent = 'Not logged in';
        }
    }
}
// Export for use in other modules
window.SessionManager = SessionManager;
