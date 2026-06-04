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
      sessionTimeout: 30 * 60 * 1000, // 30 minutes (default)
      rememberMeTimeout: 30 * 24 * 60 * 60 * 1000, // 30 days for "remember me"
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
    } else {
      localStorage.removeItem('rememberMe');
    }

    const sessionTimeout = rememberMe ? this.config.rememberMeTimeout : this.config.sessionTimeout;
    const sessionDays = sessionTimeout / (24 * 60 * 60 * 1000);

    console.log(`✅ Session started: ${rememberMe ? '30 days' : '30 minutes'} timeout (${sessionDays.toFixed(1)} days)`);

    // Set warning timer
    this.timers.warning = setTimeout(() => {
      if (this.callbacks.onSessionWarning) {
        console.log('⚠️ Session warning: 5 minutes remaining');
        this.callbacks.onSessionWarning({ timeRemaining: this.config.warningTime });
      }
    }, sessionTimeout - this.config.warningTime);

    // Set expiration timer
    this.timers.expiration = setTimeout(() => {
      console.log('❌ Session expired');
      if (this.callbacks.onSessionExpired) {
        this.callbacks.onSessionExpired();
      }
    }, sessionTimeout);
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
        const minutesUntilRefresh = Math.round(refreshAtMs / 60 / 1000);
        console.log(`🔄 Token refresh scheduled in ~${minutesUntilRefresh} minutes (expires at ${new Date(expMs).toLocaleString()})`);

        this.timers.tokenRefreshTimer = setTimeout(async () => {
          console.log('🔄 Token refresh triggered');
          if (this.authContext?.refreshSession) {
            try {
              const result = await this.authContext.refreshSession();
              if (result.success) {
                console.log('✅ Token refresh successful');
              } else {
                console.error('❌ Token refresh failed:', result.error);
              }
              if (this.callbacks.onTokenRefresh) {
                this.callbacks.onTokenRefresh(result);
              }
              if (!result.success && this.callbacks.onRefreshError) {
                this.callbacks.onRefreshError(result.error, 1);
              }
            } catch (error) {
              console.error('❌ Token refresh error:', error.message);
              if (this.callbacks.onRefreshError) {
                this.callbacks.onRefreshError(error.message, 1);
              }
            }
          }
        }, refreshAtMs);
      } else {
        console.warn('⚠️ Token already expired or expires too soon, skipping refresh timer');
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

