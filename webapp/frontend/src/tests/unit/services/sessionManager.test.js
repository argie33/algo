/**
 * Unit Tests for SessionManager
 * Tests session management with token refresh, timeout handling, and user activity tracking
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import sessionManager from "../../../services/sessionManager.js";

// Mock localStorage and sessionStorage
const mockStorage = {
  storage: {},
  setItem: vi.fn((key, value) => {
    mockStorage.storage[key] = value;
  }),
  getItem: vi.fn((key) => mockStorage.storage[key] || null),
  removeItem: vi.fn((key) => {
    delete mockStorage.storage[key];
  }),
  clear: vi.fn(() => {
    mockStorage.storage = {};
  })
};

Object.defineProperty(window, 'localStorage', { value: mockStorage });
Object.defineProperty(window, 'sessionStorage', { value: { ...mockStorage, storage: {} } });

// Mock document for event listeners
Object.defineProperty(document, 'addEventListener', {
  value: vi.fn(),
  writable: true
});

Object.defineProperty(document, 'hidden', {
  value: false,
  writable: true,
  configurable: true
});

describe("SessionManager", () => {
  let mockAuthContext;

  beforeEach(() => {
    vi.clearAllMocks();
    vi.clearAllTimers();
    vi.useFakeTimers();
    
    // Reset session manager state
    sessionManager.clearAllTimers();
    sessionManager.clearSessionStorage();
    sessionManager.sessionData = {
      lastActivity: Date.now(),
      loginTime: null,
      refreshAttempts: 0,
      rememberMe: false,
    };

    // Mock auth context
    mockAuthContext = {
      refreshSession: vi.fn().mockResolvedValue({ success: true, accessToken: "new-token" }),
      logout: vi.fn().mockResolvedValue()
    };

    mockStorage.storage = {};
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
    sessionManager.clearAllTimers();
    sessionManager.clearSessionStorage();
  });

  describe("Initialization", () => {
    it("should initialize session manager with auth context", () => {
      const consoleSpy = vi.spyOn(console, 'log').mockImplementation();
      
      sessionManager.initialize(mockAuthContext);

      expect(sessionManager.authContext).toBe(mockAuthContext);
      expect(document.addEventListener).toHaveBeenCalled();
      expect(consoleSpy).toHaveBeenCalledWith("🔐 Session manager initialized");
      
      consoleSpy.mockRestore();
    });

    it("should set up event listeners for user activity", () => {
      sessionManager.initialize(mockAuthContext);

      const expectedEvents = ["mousedown", "mousemove", "keypress", "scroll", "touchstart", "click"];
      expectedEvents.forEach(event => {
        expect(document.addEventListener).toHaveBeenCalledWith(
          event,
          expect.any(Function),
          true
        );
      });

      expect(document.addEventListener).toHaveBeenCalledWith(
        "visibilitychange",
        expect.any(Function)
      );
    });
  });

  describe("Session Management", () => {
    it("should start session without remember me", () => {
      const consoleSpy = vi.spyOn(console, 'log').mockImplementation();
      const now = Date.now();
      vi.setSystemTime(now);

      sessionManager.startSession(false);

      expect(sessionManager.sessionData.loginTime).toBe(now);
      expect(sessionManager.sessionData.lastActivity).toBe(now);
      expect(sessionManager.sessionData.rememberMe).toBe(false);
      expect(sessionManager.sessionData.refreshAttempts).toBe(0);
      
      expect(sessionStorage.setItem).toHaveBeenCalledWith("sessionStart", now.toString());
      expect(sessionStorage.setItem).toHaveBeenCalledWith("rememberMe", "false");
      
      expect(consoleSpy).toHaveBeenCalledWith("🔐 Session started (remember me: false)");
      consoleSpy.mockRestore();
    });

    it("should start session with remember me", () => {
      const consoleSpy = vi.spyOn(console, 'log').mockImplementation();
      const now = Date.now();
      vi.setSystemTime(now);

      sessionManager.startSession(true);

      expect(sessionManager.sessionData.rememberMe).toBe(true);
      expect(localStorage.setItem).toHaveBeenCalledWith("sessionStart", now.toString());
      expect(localStorage.setItem).toHaveBeenCalledWith("rememberMe", "true");
      
      expect(consoleSpy).toHaveBeenCalledWith("🔐 Session started (remember me: true)");
      consoleSpy.mockRestore();
    });

    it("should end session properly", () => {
      const consoleSpy = vi.spyOn(console, 'log').mockImplementation();
      
      sessionManager.startSession(true);
      sessionManager.endSession();

      expect(consoleSpy).toHaveBeenCalledWith("🔐 Session ended");
      consoleSpy.mockRestore();
    });

    it("should update activity timestamp", () => {
      const initialTime = Date.now();
      const laterTime = initialTime + 5000;

      sessionManager.sessionData.lastActivity = initialTime;
      
      vi.setSystemTime(laterTime);
      sessionManager.updateActivity();

      expect(sessionManager.sessionData.lastActivity).toBe(laterTime);
    });
  });

  describe("Token Refresh", () => {
    beforeEach(() => {
      sessionManager.initialize(mockAuthContext);
    });

    it("should refresh tokens successfully", async () => {
      const consoleSpy = vi.spyOn(console, 'log').mockImplementation();
      
      const onTokenRefresh = vi.fn();
      sessionManager.setCallbacks({ onTokenRefresh });

      sessionManager.sessionData.refreshAttempts = 1;
      await sessionManager.refreshTokens();

      expect(mockAuthContext.refreshSession).toHaveBeenCalled();
      expect(sessionManager.sessionData.refreshAttempts).toBe(0);
      expect(onTokenRefresh).toHaveBeenCalledWith({ success: true, accessToken: "new-token" });
      expect(consoleSpy).toHaveBeenCalledWith("✅ Tokens refreshed successfully");
      
      consoleSpy.mockRestore();
    });

    it("should handle token refresh failure", async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation();
      
      const _refreshError = new Error("Refresh failed");
      mockAuthContext.refreshSession.mockResolvedValueOnce({ success: false, error: "Network error" });

      const onRefreshError = vi.fn();
      sessionManager.setCallbacks({ onRefreshError });

      sessionManager.sessionData.refreshAttempts = 0;
      await sessionManager.refreshTokens();

      expect(sessionManager.sessionData.refreshAttempts).toBe(1);
      expect(onRefreshError).toHaveBeenCalledWith(
        expect.any(Error),
        1
      );
      
      consoleSpy.mockRestore();
    });

    it("should logout after max refresh attempts", async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation();
      
      mockAuthContext.refreshSession.mockResolvedValue({ success: false, error: "Always fails" });
      
      // Set to max-1 attempts
      sessionManager.sessionData.refreshAttempts = sessionManager.config.maxRefreshAttempts - 1;
      
      const handleSessionExpiredSpy = vi.spyOn(sessionManager, 'handleSessionExpired').mockImplementation();
      
      await sessionManager.refreshTokens();

      expect(handleSessionExpiredSpy).toHaveBeenCalled();
      expect(consoleSpy).toHaveBeenCalledWith("❌ Max refresh attempts reached, logging out");
      
      consoleSpy.mockRestore();
      handleSessionExpiredSpy.mockRestore();
    });

    it("should not refresh if already refreshing", async () => {
      sessionManager.isRefreshing = true;

      await sessionManager.refreshTokens();

      expect(mockAuthContext.refreshSession).not.toHaveBeenCalled();
    });

    it("should schedule token refresh", () => {
      const setIntervalSpy = vi.spyOn(global, 'setInterval');
      const consoleSpy = vi.spyOn(console, 'log').mockImplementation();

      sessionManager.scheduleTokenRefresh();

      expect(setIntervalSpy).toHaveBeenCalledWith(
        expect.any(Function),
        sessionManager.config.tokenRefreshInterval
      );
      expect(consoleSpy).toHaveBeenCalledWith("🔄 Token refresh scheduled");

      setIntervalSpy.mockRestore();
      consoleSpy.mockRestore();
    });
  });

  describe("Session Timeout Management", () => {
    beforeEach(() => {
      sessionManager.initialize(mockAuthContext);
    });

    it("should handle session warning", () => {
      const consoleSpy = vi.spyOn(console, 'log').mockImplementation();
      
      const onSessionWarning = vi.fn();
      sessionManager.setCallbacks({ onSessionWarning });

      sessionManager.handleSessionWarning();

      expect(onSessionWarning).toHaveBeenCalledWith({
        timeRemaining: sessionManager.config.warningTime,
        canExtend: true
      });
      expect(consoleSpy).toHaveBeenCalledWith("⚠️ Session expiring soon");
      
      consoleSpy.mockRestore();
    });

    it("should handle session expired", async () => {
      const consoleSpy = vi.spyOn(console, 'log').mockImplementation();
      
      const onSessionExpired = vi.fn();
      sessionManager.setCallbacks({ onSessionExpired });

      const endSessionSpy = vi.spyOn(sessionManager, 'endSession').mockImplementation();

      await sessionManager.handleSessionExpired();

      expect(onSessionExpired).toHaveBeenCalled();
      expect(mockAuthContext.logout).toHaveBeenCalled();
      expect(endSessionSpy).toHaveBeenCalled();
      expect(consoleSpy).toHaveBeenCalledWith("❌ Session expired");
      
      consoleSpy.mockRestore();
      endSessionSpy.mockRestore();
    });

    it("should extend session", () => {
      const consoleSpy = vi.spyOn(console, 'log').mockImplementation();
      
      const startSessionTimeoutSpy = vi.spyOn(sessionManager, 'startSessionTimeout').mockImplementation();
      const startWarningTimerSpy = vi.spyOn(sessionManager, 'startWarningTimer').mockImplementation();

      sessionManager.extendSession();

      expect(startSessionTimeoutSpy).toHaveBeenCalled();
      expect(startWarningTimerSpy).toHaveBeenCalled();
      expect(consoleSpy).toHaveBeenCalledWith("🔄 Extending session");
      
      consoleSpy.mockRestore();
      startSessionTimeoutSpy.mockRestore();
      startWarningTimerSpy.mockRestore();
    });

    it("should use different timeout duration for remember me", () => {
      const setTimeoutSpy = vi.spyOn(global, 'setTimeout');
      
      sessionManager.sessionData.rememberMe = true;
      sessionManager.startSessionTimeout();

      expect(setTimeoutSpy).toHaveBeenCalledWith(
        expect.any(Function),
        sessionManager.config.rememberMeDuration
      );

      setTimeoutSpy.mockRestore();
    });

    it("should use regular timeout duration for non-remember me", () => {
      const setTimeoutSpy = vi.spyOn(global, 'setTimeout');
      
      sessionManager.sessionData.rememberMe = false;
      sessionManager.startSessionTimeout();

      expect(setTimeoutSpy).toHaveBeenCalledWith(
        expect.any(Function),
        sessionManager.config.sessionTimeout
      );

      setTimeoutSpy.mockRestore();
    });
  });

  describe("Timer Management", () => {
    it("should clear all timers", () => {
      const clearIntervalSpy = vi.spyOn(global, 'clearInterval');
      const clearTimeoutSpy = vi.spyOn(global, 'clearTimeout');

      // Set up some mock timers
      sessionManager.refreshTimer = 123;
      sessionManager.warningTimer = 456;
      sessionManager.sessionTimeoutTimer = 789;

      sessionManager.clearAllTimers();

      expect(clearIntervalSpy).toHaveBeenCalledWith(123);
      expect(clearTimeoutSpy).toHaveBeenCalledWith(456);
      expect(clearTimeoutSpy).toHaveBeenCalledWith(789);

      expect(sessionManager.refreshTimer).toBeNull();
      expect(sessionManager.warningTimer).toBeNull();
      expect(sessionManager.sessionTimeoutTimer).toBeNull();

      clearIntervalSpy.mockRestore();
      clearTimeoutSpy.mockRestore();
    });

    it("should handle clearing null timers", () => {
      const clearIntervalSpy = vi.spyOn(global, 'clearInterval');
      const clearTimeoutSpy = vi.spyOn(global, 'clearTimeout');

      sessionManager.refreshTimer = null;
      sessionManager.warningTimer = null;
      sessionManager.sessionTimeoutTimer = null;

      // Should not throw or call clear functions
      expect(() => sessionManager.clearAllTimers()).not.toThrow();

      clearIntervalSpy.mockRestore();
      clearTimeoutSpy.mockRestore();
    });
  });

  describe("Session Storage Management", () => {
    it("should clear session storage", () => {
      sessionManager.clearSessionStorage();

      expect(localStorage.removeItem).toHaveBeenCalledWith("sessionStart");
      expect(localStorage.removeItem).toHaveBeenCalledWith("rememberMe");
      expect(sessionStorage.removeItem).toHaveBeenCalledWith("sessionStart");
      expect(sessionStorage.removeItem).toHaveBeenCalledWith("rememberMe");
    });
  });

  describe("Session Information", () => {
    it("should get session info", () => {
      const now = Date.now();
      const loginTime = now - 60000; // 1 minute ago
      const lastActivity = now - 30000; // 30 seconds ago

      vi.setSystemTime(now);
      
      sessionManager.sessionData = {
        loginTime,
        lastActivity,
        rememberMe: false,
        refreshAttempts: 2
      };

      const info = sessionManager.getSessionInfo();

      expect(info.isActive).toBe(true);
      expect(info.sessionDuration).toBe(60000);
      expect(info.lastActivity).toBe(lastActivity);
      expect(info.rememberMe).toBe(false);
      expect(info.refreshAttempts).toBe(2);
      expect(info.timeRemaining).toBe(sessionManager.config.sessionTimeout - 60000);
    });

    it("should check if session is valid", () => {
      const now = Date.now();
      
      // Valid session
      sessionManager.sessionData = {
        loginTime: now - 60000, // 1 minute ago
        rememberMe: false
      };
      vi.setSystemTime(now);

      expect(sessionManager.isSessionValid()).toBe(true);

      // Invalid session (expired)
      sessionManager.sessionData = {
        loginTime: now - (9 * 60 * 60 * 1000), // 9 hours ago
        rememberMe: false
      };

      expect(sessionManager.isSessionValid()).toBe(false);
    });

    it("should use remember me duration for validation", () => {
      const now = Date.now();
      
      sessionManager.sessionData = {
        loginTime: now - (20 * 24 * 60 * 60 * 1000), // 20 days ago
        rememberMe: true
      };
      vi.setSystemTime(now);

      // Should still be valid with remember me (30 days)
      expect(sessionManager.isSessionValid()).toBe(true);

      // Would be invalid without remember me
      sessionManager.sessionData.rememberMe = false;
      expect(sessionManager.isSessionValid()).toBe(false);
    });
  });

  describe("Callback Management", () => {
    it("should set and merge callbacks", () => {
      const callbacks1 = {
        onTokenRefresh: vi.fn(),
        onSessionWarning: vi.fn()
      };

      const callbacks2 = {
        onSessionExpired: vi.fn(),
        onRefreshError: vi.fn()
      };

      sessionManager.setCallbacks(callbacks1);
      expect(sessionManager.callbacks.onTokenRefresh).toBe(callbacks1.onTokenRefresh);
      expect(sessionManager.callbacks.onSessionWarning).toBe(callbacks1.onSessionWarning);

      sessionManager.setCallbacks(callbacks2);
      expect(sessionManager.callbacks.onTokenRefresh).toBe(callbacks1.onTokenRefresh); // Should be preserved
      expect(sessionManager.callbacks.onSessionExpired).toBe(callbacks2.onSessionExpired);
      expect(sessionManager.callbacks.onRefreshError).toBe(callbacks2.onRefreshError);
    });

    it("should handle missing callbacks gracefully", async () => {
      sessionManager.initialize(mockAuthContext);
      
      // Clear callbacks
      sessionManager.callbacks = {
        onTokenRefresh: null,
        onSessionWarning: null,
        onSessionExpired: null,
        onRefreshError: null,
      };

      // These should not throw
      await sessionManager.refreshTokens();
      sessionManager.handleSessionWarning();
      await sessionManager.handleSessionExpired();
    });
  });
});