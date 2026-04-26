/**
 * Session Manager - Handles user session lifecycle
 * Manages timeouts, warnings, and session persistence
 */

class SessionManager {
  constructor() {
    this.callbacks = {
      onWarning: null,
      onExpire: null,
      onExtend: null,
    };
    this.timers = {
      warning: null,
      expiration: null,
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
      if (this.callbacks.onWarning) {
        this.callbacks.onWarning();
      }
    }, this.config.sessionTimeout - this.config.warningTime);

    // Set expiration timer
    this.timers.expiration = setTimeout(() => {
      if (this.callbacks.onExpire) {
        this.callbacks.onExpire();
      }
    }, this.config.sessionTimeout);
  }

  endSession() {
    this.clearAllTimers();
    sessionStorage.removeItem('sessionData');
    localStorage.removeItem('rememberMe');
  }

  extendSession() {
    this.startSession(localStorage.getItem('rememberMe') === 'true');

    if (this.callbacks.onExtend) {
      this.callbacks.onExtend();
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
