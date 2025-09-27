/**
 * Session Management Module
 * Handles user session state and authentication
 */
class SessionManager {
    constructor() {
        this.currentSession = this.loadSession();
    }

    // Load session from localStorage
    loadSession() {
        try {
            const raw = localStorage.getItem('documentBot_session');
            if (!raw) return null;

            const session = JSON.parse(raw);

            // Expiry check
            if (session.expiresAt && new Date() > new Date(session.expiresAt)) {
                this.clearSession();
                return null;
            }
            return session;
        } catch {
            this.clearSession();
            return null;
        }
    }

    // Save / clear session
    clearSession() {
        localStorage.removeItem('documentBot_session');
        this.currentSession = null;
    }

    logout() {
        this.clearSession();
        window.location.href = '../login.html';
    }

    // Validation helpers
    isValidSession() {
        const s = this.currentSession;
        return !!(s && s.sessionId && s.user && s.isLoggedIn === true);
    }

    async validateSession() {
        return this.isValidSession();
    }

    // ✅ NEW — easy way to get just the sessionId
    getSessionId() {
        return this.isValidSession() ? this.currentSession.sessionId : null;
    }

    // Headers for API requests
    getAuthHeaders() {
        if (!this.isValidSession()) return {};
        const { sessionId, user } = this.currentSession;
        return {
            'Authorization': `Bearer ${sessionId}`,
            'X-Session-ID': sessionId,
            'X-User-ID': user?.username || 'anonymous'
        };
    }

    // UI updates
    updateUserInfo() {
        const el = document.getElementById('userInfo');
        if (!el) return;
        if (this.isValidSession()) {
            el.textContent = `Welcome, ${this.currentSession.user.username || 'User'}`;
        } else {
            el.textContent = 'Not logged in';
        }
    }
}

// Export class globally (optional for debugging, but not needed by other modules)
window.SessionManager = SessionManager;
