/**
 * Comprehensive Request Audit Logging Middleware
 * Logs all API requests with user, method, path, status, and timing for compliance
 * Meets SEC/FINRA audit requirements for activity tracking
 */

const auditLogger = (req, res, next) => {
  const requestStart = Date.now();
  const requestId =
    req.requestId ||
    `req-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
  req.requestId = requestId;

  const clientIp = req.ip || req.connection?.remoteAddress || "unknown";
  const userId = req.user?.sub || req.user?.id || "unauthenticated";
  const userEmail = req.user?.email || null;
  const userRole = req.user?.role || null;

  // Override res.end to capture status and response time
  const originalEnd = res.end;
  res.end = function (chunk, encoding) {
    const duration = Date.now() - requestStart;
    const statusCode = res.statusCode;

    // Create audit log entry
    const auditLog = {
      timestamp: new Date().toISOString(),
      requestId,
      userId,
      userEmail,
      userRole,
      method: req.method,
      path: req.path,
      url: req.originalUrl,
      statusCode,
      duration: `${duration}ms`,
      durationMs: duration,
      ipAddress: clientIp,
      userAgent: req.get("User-Agent") || null,
      // Only log request body for non-sensitive endpoints
      bodySize: req.get("Content-Length") || null,
      // Capture response size if available
      responseSize: chunk ? Buffer.byteLength(chunk) : 0,
    };

    // Log to CloudWatch with severity based on status code
    if (statusCode >= 500) {
      console.error("[AUDIT_ERROR]", JSON.stringify(auditLog));
    } else if (statusCode >= 400) {
      console.warn("[AUDIT_WARNING]", JSON.stringify(auditLog));
    } else {
      console.log("[AUDIT_INFO]", JSON.stringify(auditLog));
    }

    // Flag slow requests for performance monitoring
    if (duration > 5000) {
      console.warn(
        "[AUDIT_SLOW_REQUEST]",
        JSON.stringify({
          ...auditLog,
          warning: `Request exceeded 5 second threshold`,
        })
      );
    }

    // Call original end method
    originalEnd.call(res, chunk, encoding);
  };

  // Also override json method for comprehensive logging
  const originalJson = res.json.bind(res);
  res.json = function (data) {
    const duration = Date.now() - requestStart;
    const statusCode = res.statusCode;

    const auditLog = {
      timestamp: new Date().toISOString(),
      requestId,
      userId,
      userEmail,
      userRole,
      method: req.method,
      path: req.path,
      url: req.originalUrl,
      statusCode,
      duration: `${duration}ms`,
      durationMs: duration,
      ipAddress: clientIp,
      userAgent: req.get("User-Agent") || null,
      responseSize: data ? Buffer.byteLength(JSON.stringify(data)) : 0,
    };

    // Log to CloudWatch
    if (statusCode >= 500) {
      console.error("[AUDIT_ERROR]", JSON.stringify(auditLog));
    } else if (statusCode >= 400) {
      console.warn("[AUDIT_WARNING]", JSON.stringify(auditLog));
    } else {
      console.log("[AUDIT_INFO]", JSON.stringify(auditLog));
    }

    // Flag slow requests
    if (duration > 5000) {
      console.warn(
        "[AUDIT_SLOW_REQUEST]",
        JSON.stringify({
          ...auditLog,
          warning: `Request exceeded 5 second threshold`,
        })
      );
    }

    return originalJson(data);
  };

  next();
};

module.exports = auditLogger;
