/**
 * Session Manager - Handles user session lifecycle
 * Manages timeouts, warnings, and session persistence
 */

class SessionManager {
  constructor() {
    this.callbacks = {
      onSessionWarning: null,
      onSessionExpired: null,
      onTokenRefresh: null,
      onRefreshError: null,
    };
    this.timers = {
      warning: null,
      expiration: null,
      tokenRefreshTimer: null,
    };
    this.sessionData = null;
    this.config = {
      sessionTimeout: 30 * 60 * 1000, // 30 minutes
      warningTime: 5 * 60 * 1000, // 5 minutes before expiration
    };
  }

  initialize(authContext) {
    this.authContext = authContext;
    // Initialize session from stored data if available
    const storedSession = sessionStorage.getItem('sessionData');
    if (storedSession) {
      try {
        this.sessionData = JSON.parse(storedSession);
      } catch (e) {
        console.warn('Could not parse stored session data');
      }
    }
  }

  setCallbacks(callbacks) {
    if (callbacks) {
      this.callbacks = { ...this.callbacks, ...callbacks };
    }
  }

  startSession(rememberMe = false) {
    this.clearAllTimers();

    if (rememberMe) {
      localStorage.setItem('rememberMe', 'true');
    }

    // Set warning timer
    this.timers.warning = setTimeout(() => {
      if (this.callbacks.onSessionWarning) {
        this.callbacks.onSessionWarning({ timeRemaining: this.config.warningTime });
      }
    }, this.config.sessionTimeout - this.config.warningTime);

    // Set expiration timer
    this.timers.expiration = setTimeout(() => {
      if (this.callbacks.onSessionExpired) {
        this.callbacks.onSessionExpired();
      }
    }, this.config.sessionTimeout);
  }

  endSession() {
    this.clearAllTimers();
    sessionStorage.removeItem('sessionData');
    localStorage.removeItem('rememberMe');
  }

  startTokenRefreshTimer(accessToken) {
    if (this.timers.tokenRefreshTimer) {
      clearTimeout(this.timers.tokenRefreshTimer);
      this.timers.tokenRefreshTimer = null;
    }

    if (!accessToken) return;

    try {
      const parts = accessToken.split('.');
      if (parts.length !== 3) return;

      const payload = JSON.parse(atob(parts[1]));
      const expMs = payload.exp * 1000;
      const nowMs = Date.now();
      const refreshEarlyMs = 5 * 60 * 1000; // refresh 5 minutes before expiry
      const refreshAtMs = expMs - nowMs - refreshEarlyMs;

      if (refreshAtMs > 0) {
        this.timers.tokenRefreshTimer = setTimeout(async () => {
          if (this.authContext?.refreshSession) {
            try {
              const result = await this.authContext.refreshSession();
              if (this.callbacks.onTokenRefresh) {
                this.callbacks.onTokenRefresh(result);
              }
              if (!result.success && this.callbacks.onRefreshError) {
                this.callbacks.onRefreshError(result.error, 1);
              }
            } catch (error) {
              if (this.callbacks.onRefreshError) {
                this.callbacks.onRefreshError(error.message, 1);
              }
            }
          }
        }, refreshAtMs);
      }
    } catch (e) {
      console.warn('Could not parse token expiry for refresh timer', e);
    }
  }

  extendSession() {
    this.startSession(localStorage.getItem('rememberMe') === 'true');

    if (this.callbacks.onTokenRefresh) {
      this.callbacks.onTokenRefresh(null);
    }
  }

  clearAllTimers() {
    if (this.timers.warning) {
      clearTimeout(this.timers.warning);
      this.timers.warning = null;
    }
    if (this.timers.expiration) {
      clearTimeout(this.timers.expiration);
      this.timers.expiration = null;
    }
    if (this.timers.tokenRefreshTimer) {
      clearTimeout(this.timers.tokenRefreshTimer);
      this.timers.tokenRefreshTimer = null;
    }
  }

  getSessionInfo() {
    return {
      isActive: !!(this.timers.warning || this.timers.expiration),
      sessionData: this.sessionData,
    };
  }
}

// Export singleton instance
export default new SessionManager();
