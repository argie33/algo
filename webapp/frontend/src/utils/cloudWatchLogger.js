/**
 * CloudWatch Error Logger
 * Sends frontend errors to AWS CloudWatch for production monitoring
 *
 * All errors are logged with context:
 * - User/session ID
 * - Page/component that failed
 * - Error type and message
 * - Browser/environment info
 *
 * Log group: /aws/frontend/algo-trading-dashboard
 * Log stream: {environment}/{userId}
 */

import { v4 as uuidv4 } from "uuid";

class CloudWatchLogger {
  constructor() {
    this.sessionId = uuidv4();
    this.userId = null;
    this.environment = process.env.NODE_ENV || "unknown";
    this.logBuffer = [];
    this.flushInterval = 5000; // Flush every 5 seconds
    this.isInitialized = false;
    this.apiEndpoint = process.env.REACT_APP_API_URL || "";

    this.startFlushTimer();
  }

  /**
   * Initialize logger with user info (call after auth is available)
   */
  setUser(userId) {
    this.userId = userId;
  }

  /**
   * Log an error to CloudWatch
   */
  logError(component, operation, error, context = {}) {
    if (!error) return;

    const errorEntry = {
      timestamp: new Date().toISOString(),
      level: "ERROR",
      sessionId: this.sessionId,
      userId: this.userId || "anonymous",
      component,
      operation,
      environment: this.environment,
      errorType: error.name || typeof error,
      errorMessage: error.message || String(error),
      errorStack: error.stack || "",
      url: window.location.href,
      userAgent: navigator.userAgent,
      context,
    };

    // Add to buffer for batch sending
    this.logBuffer.push(errorEntry);

    // Also log to browser console in development
    if (this.environment === "development") {
      console.error(`[CloudWatch] ${component}/${operation}:`, errorEntry);
    }

    // If this is a critical error, flush immediately
    if (this.isCriticalError(error)) {
      this.flush();
    }
  }

  /**
   * Log a warning
   */
  logWarn(component, message, context = {}) {
    const warnEntry = {
      timestamp: new Date().toISOString(),
      level: "WARN",
      sessionId: this.sessionId,
      userId: this.userId || "anonymous",
      component,
      message,
      environment: this.environment,
      url: window.location.href,
      context,
    };

    this.logBuffer.push(warnEntry);
  }

  /**
   * Log an API error with request/response details
   */
  logApiError(component, operation, response, requestContext = {}) {
    const apiError = {
      timestamp: new Date().toISOString(),
      level: "ERROR",
      type: "API_ERROR",
      sessionId: this.sessionId,
      userId: this.userId || "anonymous",
      component,
      operation,
      environment: this.environment,
      statusCode: response?.status,
      statusText: response?.statusText,
      endpoint: response?.config?.url,
      method: response?.config?.method,
      errorMessage:
        response?.data?.message || response?.statusText || "Unknown error",
      url: window.location.href,
      context: requestContext,
    };

    this.logBuffer.push(apiError);

    // Flush critical API errors immediately
    if (response?.status >= 500) {
      this.flush();
    }
  }

  /**
   * Determine if error needs immediate flush
   */
  isCriticalError(error) {
    const criticalPatterns = [
      "Cannot read properties of undefined",
      "is not a function",
      "is not defined",
      "null reference",
      "ReferenceError",
      "TypeError: Cannot",
    ];

    const errorStr = String(error);
    return criticalPatterns.some((pattern) => errorStr.includes(pattern));
  }

  /**
   * Send buffered logs to CloudWatch (via Lambda)
   */
  async flush() {
    if (this.logBuffer.length === 0) return;

    const logsToSend = [...this.logBuffer];
    this.logBuffer = []; // Clear buffer

    try {
      const response = await fetch(`${this.apiEndpoint}/api/logs`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          logs: logsToSend,
          sessionId: this.sessionId,
          userId: this.userId || "anonymous",
          environment: this.environment,
        }),
      });

      if (!response.ok) {
        console.warn(
          "[CloudWatchLogger] Failed to send logs:",
          response.status
        );
        // Re-queue logs for next attempt (don't lose them)
        this.logBuffer.unshift(...logsToSend);
      }
    } catch (err) {
      console.warn("[CloudWatchLogger] Network error sending logs:", err);
      // Re-queue for retry
      this.logBuffer.unshift(...logsToSend);
    }
  }

  /**
   * Start periodic flush timer
   */
  startFlushTimer() {
    setInterval(() => {
      this.flush();
    }, this.flushInterval);

    // Also flush on page unload
    window.addEventListener("beforeunload", () => {
      this.flush();
    });
  }

  /**
   * Get session ID (useful for linking logs to user reports)
   */
  getSessionId() {
    return this.sessionId;
  }
}

// Create singleton instance
const cloudWatchLogger = new CloudWatchLogger();

export default cloudWatchLogger;
