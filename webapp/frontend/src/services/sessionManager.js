/**
 * Session Management Service
 * Handles token refresh, session timeout, and automatic logout
 */

class SessionManager {
  constructor() {
    this.refreshTimer = null;
    this.warningTimer = null;
    this.sessionTimeoutTimer = null;
    this.isRefreshing = false;

    // Configuration
    this.config = {
      tokenRefreshInterval: 45 * 60 * 1000, // 45 minutes
      sessionTimeout: 8 * 60 * 60 * 1000, // 8 hours
      warningTime: 10 * 60 * 1000, // 10 minutes before timeout
      maxRefreshAttempts: 3,
      rememberMeDuration: 30 * 24 * 60 * 60 * 1000, // 30 days
    };

    this.callbacks = {
      onTokenRefresh: null,
      onSessionWarning: null,
      onSessionExpired: null,
      onRefreshError: null,
    };

    this.sessionData = {
      lastActivity: Date.now(),
      loginTime: null,
      refreshAttempts: 0,
      rememberMe: false,
    };
  }

  /**
   * Initialize session management
   */
  initialize(authContext) {
    this.authContext = authContext;
    this.setupEventListeners();
    this.startSessionTracking();
    this.scheduleTokenRefresh();

    // Session manager initialized
  }

  /**
   * Set callback functions
   */
  setCallbacks(callbacks) {
    this.callbacks = { ...this.callbacks, ...callbacks };
  }

  /**
   * Start a new session
   */
  startSession(rememberMe = false) {
    const now = Date.now();
    this.sessionData = {
      lastActivity: now,
      loginTime: now,
      refreshAttempts: 0,
      rememberMe,
    };

    // Store session info
    const storage = rememberMe ? localStorage : sessionStorage;
    storage.setItem("sessionStart", now.toString());
    storage.setItem("rememberMe", rememberMe.toString());

    this.startSessionTracking();
    this.scheduleTokenRefresh();

    // Session started
  }

  /**
   * End the current session
   */
  endSession() {
    this.clearAllTimers();
    this.clearSessionStorage();

    // Session ended
  }

  /**
   * Update last activity timestamp
   */
  updateActivity() {
    this.sessionData.lastActivity = Date.now();

    // Reset session timeout if user is active
    if (this.sessionTimeoutTimer) {
      clearTimeout(this.sessionTimeoutTimer);
      this.startSessionTimeout();
    }
  }

  /**
   * Schedule automatic token refresh
   */
  scheduleTokenRefresh() {
    if (this.refreshTimer) {
      clearInterval(this.refreshTimer);
    }

    this.refreshTimer = setInterval(async () => {
      await this.refreshTokens();
    }, this.config.tokenRefreshInterval);

    // Token refresh scheduled
  }

  /**
   * Refresh authentication tokens
   */
  async refreshTokens() {
    if (this.isRefreshing || !this.authContext) {
      return;
    }

    this.isRefreshing = true;

    try {
      // Refreshing tokens

      const result = await this.authContext.refreshSession();

      if (result.success) {
        this.sessionData.refreshAttempts = 0;
        // Tokens refreshed successfully

        if (this.callbacks.onTokenRefresh) {
          this.callbacks.onTokenRefresh(result);
        }
      } else {
        throw new Error(result.error || "Token refresh failed");
      }
    } catch (error) {
      console.error("❌ Token refresh failed:", error);
      this.sessionData.refreshAttempts++;

      if (this.callbacks.onRefreshError) {
        this.callbacks.onRefreshError(error, this.sessionData.refreshAttempts);
      }

      // If max attempts reached, logout user
      if (this.sessionData.refreshAttempts >= this.config.maxRefreshAttempts) {
        console.error("❌ Max refresh attempts reached, logging out");
        await this.handleSessionExpired();
      }
    } finally {
      this.isRefreshing = false;
    }
  }

  /**
   * Start session timeout tracking
   */
  startSessionTracking() {
    this.startSessionTimeout();
    this.startWarningTimer();
  }

  /**
   * Start session timeout timer
   */
  startSessionTimeout() {
    if (this.sessionTimeoutTimer) {
      clearTimeout(this.sessionTimeoutTimer);
    }

    const timeoutDuration = this.sessionData.rememberMe
      ? this.config.rememberMeDuration
      : this.config.sessionTimeout;

    this.sessionTimeoutTimer = setTimeout(async () => {
      await this.handleSessionExpired();
    }, timeoutDuration);
  }

  /**
   * Start warning timer
   */
  startWarningTimer() {
    if (this.warningTimer) {
      clearTimeout(this.warningTimer);
    }

    const timeoutDuration = this.sessionData.rememberMe
      ? this.config.rememberMeDuration
      : this.config.sessionTimeout;

    const warningTime = timeoutDuration - this.config.warningTime;

    this.warningTimer = setTimeout(() => {
      this.handleSessionWarning();
    }, warningTime);
  }

  /**
   * Handle session warning
   */
  handleSessionWarning() {
    // Session expiring soon

    if (this.callbacks.onSessionWarning) {
      this.callbacks.onSessionWarning({
        timeRemaining: this.config.warningTime,
        canExtend: true,
      });
    }
  }

  /**
   * Handle session expired
   */
  async handleSessionExpired() {
    // Session expired

    if (this.callbacks.onSessionExpired) {
      this.callbacks.onSessionExpired();
    }

    // Logout user
    if (this.authContext) {
      await this.authContext.logout();
    }

    this.endSession();
  }

  /**
   * Extend session when user is active
   */
  extendSession() {
    // Extending session
    this.updateActivity();

    // Restart timers
    this.startSessionTimeout();
    this.startWarningTimer();
  }

  /**
   * Setup event listeners for user activity
   */
  setupEventListeners() {
    const events = [
      "mousedown",
      "mousemove",
      "keypress",
      "scroll",
      "touchstart",
      "click",
    ];

    const activityHandler = () => {
      this.updateActivity();
    };

    events.forEach((event) => {
      document.addEventListener(event, activityHandler, true);
    });

    // Listen for page visibility changes
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) {
        this.updateActivity();
      }
    });
  }

  /**
   * Clear all timers
   */
  clearAllTimers() {
    if (this.refreshTimer) {
      clearInterval(this.refreshTimer);
      this.refreshTimer = null;
    }

    if (this.warningTimer) {
      clearTimeout(this.warningTimer);
      this.warningTimer = null;
    }

    if (this.sessionTimeoutTimer) {
      clearTimeout(this.sessionTimeoutTimer);
      this.sessionTimeoutTimer = null;
    }
  }

  /**
   * Clear session storage
   */
  clearSessionStorage() {
    localStorage.removeItem("sessionStart");
    localStorage.removeItem("rememberMe");
    sessionStorage.removeItem("sessionStart");
    sessionStorage.removeItem("rememberMe");
  }

  /**
   * Get session info
   */
  getSessionInfo() {
    const now = Date.now();
    const sessionDuration = now - (this.sessionData.loginTime || now);
    const timeoutDuration = this.sessionData.rememberMe
      ? this.config.rememberMeDuration
      : this.config.sessionTimeout;

    return {
      isActive: true,
      sessionDuration,
      timeRemaining: timeoutDuration - sessionDuration,
      lastActivity: this.sessionData.lastActivity,
      rememberMe: this.sessionData.rememberMe,
      refreshAttempts: this.sessionData.refreshAttempts,
    };
  }

  /**
   * Check if session is valid
   */
  isSessionValid() {
    const now = Date.now();
    const sessionAge = now - (this.sessionData.loginTime || now);
    const maxAge = this.sessionData.rememberMe
      ? this.config.rememberMeDuration
      : this.config.sessionTimeout;

    return sessionAge < maxAge;
  }
}

// Create singleton instance
const sessionManager = new SessionManager();

export default sessionManager;
