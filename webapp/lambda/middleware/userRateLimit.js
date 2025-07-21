/**
 * User-Specific Rate Limiting Middleware
 * 
 * Implements sophisticated rate limiting per authenticated user to prevent abuse
 * while allowing legitimate high-frequency trading operations.
 */

const jwt = require('aws-jwt-verify');

// In-memory store for rate limiting (suitable for Lambda)
// In production, consider Redis for multi-instance deployments
const userRateLimits = new Map();
const userRequestHistory = new Map();
const suspiciousActivity = new Map();

// Rate limit configurations per user type and endpoint category
const RATE_LIMIT_CONFIGS = {
  // Different user tiers with different limits
  free: {
    api: { windowMs: 60 * 1000, maxRequests: 50 },
    trading: { windowMs: 60 * 1000, maxRequests: 20 },
    market_data: { windowMs: 60 * 1000, maxRequests: 100 },
    portfolio: { windowMs: 60 * 1000, maxRequests: 30 }
  },
  premium: {
    api: { windowMs: 60 * 1000, maxRequests: 200 },
    trading: { windowMs: 60 * 1000, maxRequests: 100 },
    market_data: { windowMs: 60 * 1000, maxRequests: 500 },
    portfolio: { windowMs: 60 * 1000, maxRequests: 150 }
  },
  professional: {
    api: { windowMs: 60 * 1000, maxRequests: 1000 },
    trading: { windowMs: 60 * 1000, maxRequests: 500 },
    market_data: { windowMs: 60 * 1000, maxRequests: 2000 },
    portfolio: { windowMs: 60 * 1000, maxRequests: 500 }
  }
};

// Suspicious activity thresholds
const SUSPICIOUS_THRESHOLDS = {
  rapidRequests: 50, // More than 50 requests in 10 seconds
  errorRate: 0.5, // More than 50% error rate
  uniqueEndpoints: 20 // Accessing more than 20 different endpoints in 1 minute
};

/**
 * Create user-specific rate limiting middleware
 */
function createUserRateLimit(category = 'api') {
  return async (req, res, next) => {
    try {
      // Extract user ID from JWT token
      const userId = await getUserIdFromRequest(req);
      
      if (!userId) {
        // If no user ID, apply stricter anonymous rate limiting
        return applyAnonymousRateLimit(req, res, next, category);
      }

      // Get user tier (default to free if not specified)
      const userTier = await getUserTier(userId);
      
      // Apply user-specific rate limiting
      const rateLimitResult = await applyUserRateLimit(userId, userTier, category, req);
      
      if (!rateLimitResult.allowed) {
        return res.status(429).json({
          success: false,
          error: 'Rate limit exceeded',
          message: rateLimitResult.message,
          retryAfter: rateLimitResult.retryAfter,
          limits: rateLimitResult.limits,
          usage: rateLimitResult.usage,
          timestamp: new Date().toISOString()
        });
      }

      // Track request for suspicious activity detection
      trackUserActivity(userId, req, rateLimitResult);

      // Add rate limit headers
      res.set({
        'X-RateLimit-Limit': rateLimitResult.limits.maxRequests,
        'X-RateLimit-Remaining': rateLimitResult.limits.remaining,
        'X-RateLimit-Reset': rateLimitResult.limits.resetTime,
        'X-RateLimit-Category': category,
        'X-User-Tier': userTier
      });

      next();

    } catch (error) {
      console.error('User rate limiting error:', error);
      // Don't fail the request due to rate limiting errors
      next();
    }
  };
}

/**
 * Extract user ID from JWT token in request
 */
async function getUserIdFromRequest(req) {
  try {
    const authHeader = req.headers.authorization;
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return null;
    }

    const token = authHeader.substring(7);
    
    // Verify JWT token
    const verifier = jwt.CognitoJwtVerifier.create({
      userPoolId: process.env.COGNITO_USER_POOL_ID,
      tokenUse: 'access',
      clientId: process.env.COGNITO_CLIENT_ID
    });

    const payload = await verifier.verify(token);
    return payload.sub; // User ID

  } catch (error) {
    // Invalid or expired token
    return null;
  }
}

/**
 * Get user tier from user ID (could be from database or user attributes)
 */
async function getUserTier(userId) {
  // For now, return 'free' as default
  // In production, this would query user's subscription tier from database
  return 'free';
}

/**
 * Apply rate limiting for authenticated users
 */
async function applyUserRateLimit(userId, userTier, category, req) {
  const now = Date.now();
  const config = RATE_LIMIT_CONFIGS[userTier]?.[category] || RATE_LIMIT_CONFIGS.free[category];
  
  if (!config) {
    // No rate limiting for unknown categories
    return { allowed: true, limits: {}, usage: {} };
  }

  const windowMs = config.windowMs;
  const maxRequests = config.maxRequests;
  const key = `${userId}:${category}`;

  // Initialize user rate limit data if not exists
  if (!userRateLimits.has(key)) {
    userRateLimits.set(key, {
      requests: [],
      firstRequest: now,
      lastRequest: now,
      totalRequests: 0,
      blockedRequests: 0
    });
  }

  const userLimit = userRateLimits.get(key);
  
  // Clean old requests outside the current window
  userLimit.requests = userLimit.requests.filter(time => now - time < windowMs);
  
  // Check if rate limit exceeded
  if (userLimit.requests.length >= maxRequests) {
    userLimit.blockedRequests++;
    
    const oldestRequest = Math.min(...userLimit.requests);
    const retryAfter = Math.ceil((oldestRequest + windowMs - now) / 1000);

    return {
      allowed: false,
      message: `Rate limit exceeded for ${category} endpoints. You've made ${userLimit.requests.length} requests in the last ${windowMs/1000} seconds (limit: ${maxRequests}).`,
      retryAfter,
      limits: {
        maxRequests,
        windowMs,
        resetTime: new Date(oldestRequest + windowMs).toISOString()
      },
      usage: {
        current: userLimit.requests.length,
        total: userLimit.totalRequests,
        blocked: userLimit.blockedRequests
      }
    };
  }

  // Allow request and record it
  userLimit.requests.push(now);
  userLimit.lastRequest = now;
  userLimit.totalRequests++;

  return {
    allowed: true,
    limits: {
      maxRequests,
      remaining: maxRequests - userLimit.requests.length,
      resetTime: new Date(now + windowMs).toISOString()
    },
    usage: {
      current: userLimit.requests.length,
      total: userLimit.totalRequests,
      blocked: userLimit.blockedRequests
    }
  };
}

/**
 * Apply rate limiting for anonymous users (stricter limits)
 */
function applyAnonymousRateLimit(req, res, next, category) {
  const { getClientIP } = require('../utils/ipDetection');
  const clientIP = getClientIP(req);
  const now = Date.now();
  const key = `anonymous:${clientIP}:${category}`;
  
  // Strict limits for anonymous users
  const maxRequests = 10; // Very limited for anonymous
  const windowMs = 60 * 1000; // 1 minute

  if (!userRateLimits.has(key)) {
    userRateLimits.set(key, { requests: [], blockedRequests: 0 });
  }

  const userLimit = userRateLimits.get(key);
  userLimit.requests = userLimit.requests.filter(time => now - time < windowMs);

  if (userLimit.requests.length >= maxRequests) {
    userLimit.blockedRequests++;
    
    return res.status(429).json({
      success: false,
      error: 'Rate limit exceeded',
      message: 'Please authenticate to access higher rate limits',
      retryAfter: 60,
      limits: { maxRequests, current: userLimit.requests.length }
    });
  }

  userLimit.requests.push(now);
  
  res.set({
    'X-RateLimit-Limit': maxRequests,
    'X-RateLimit-Remaining': maxRequests - userLimit.requests.length,
    'X-User-Tier': 'anonymous'
  });

  next();
}

/**
 * Track user activity for suspicious behavior detection
 */
function trackUserActivity(userId, req, rateLimitResult) {
  const now = Date.now();
  const key = userId;

  if (!userRequestHistory.has(key)) {
    userRequestHistory.set(key, {
      requests: [],
      endpoints: new Set(),
      errors: 0,
      lastActivity: now
    });
  }

  const history = userRequestHistory.get(key);
  
  // Track request
  history.requests.push({
    timestamp: now,
    endpoint: req.path,
    method: req.method,
    userAgent: req.headers['user-agent'] || 'unknown'
  });

  // Track unique endpoints
  history.endpoints.add(`${req.method} ${req.path}`);
  history.lastActivity = now;

  // Clean old history (keep last 10 minutes)
  const tenMinutesAgo = now - (10 * 60 * 1000);
  history.requests = history.requests.filter(r => r.timestamp > tenMinutesAgo);

  // Clean old endpoints (reset every hour)
  const oneHourAgo = now - (60 * 60 * 1000);
  if (history.lastEndpointReset && now - history.lastEndpointReset > oneHourAgo) {
    history.endpoints.clear();
    history.lastEndpointReset = now;
  }

  // Check for suspicious activity
  detectSuspiciousActivity(userId, history);
}

/**
 * Detect suspicious user activity patterns
 */
function detectSuspiciousActivity(userId, history) {
  const now = Date.now();
  const tenSecondsAgo = now - (10 * 1000);
  const oneMinuteAgo = now - (60 * 1000);

  // Check for rapid requests
  const recentRequests = history.requests.filter(r => r.timestamp > tenSecondsAgo);
  if (recentRequests.length > SUSPICIOUS_THRESHOLDS.rapidRequests) {
    markSuspiciousActivity(userId, 'rapid_requests', {
      count: recentRequests.length,
      threshold: SUSPICIOUS_THRESHOLDS.rapidRequests
    });
  }

  // Check for accessing too many unique endpoints
  const recentEndpoints = new Set(
    history.requests
      .filter(r => r.timestamp > oneMinuteAgo)
      .map(r => r.endpoint)
  );
  
  if (recentEndpoints.size > SUSPICIOUS_THRESHOLDS.uniqueEndpoints) {
    markSuspiciousActivity(userId, 'endpoint_scanning', {
      count: recentEndpoints.size,
      threshold: SUSPICIOUS_THRESHOLDS.uniqueEndpoints
    });
  }
}

/**
 * Mark suspicious activity for a user
 */
function markSuspiciousActivity(userId, type, details) {
  const now = Date.now();
  
  if (!suspiciousActivity.has(userId)) {
    suspiciousActivity.set(userId, []);
  }

  const activities = suspiciousActivity.get(userId);
  activities.push({
    type,
    details,
    timestamp: now
  });

  // Keep only recent suspicious activities (last hour)
  const oneHourAgo = now - (60 * 60 * 1000);
  suspiciousActivity.set(userId, activities.filter(a => a.timestamp > oneHourAgo));

  console.warn(`🚨 Suspicious activity detected for user ${userId.substring(0, 8)}...: ${type}`, details);
}

/**
 * Get rate limiting statistics for monitoring
 */
function getRateLimitStats() {
  const now = Date.now();
  const activeUsers = new Set();
  const blockedUsers = new Set();
  let totalRequests = 0;
  let totalBlocked = 0;

  for (const [key, data] of userRateLimits.entries()) {
    const [userId] = key.split(':');
    activeUsers.add(userId);
    totalRequests += data.totalRequests || 0;
    totalBlocked += data.blockedRequests || 0;
    
    if (data.blockedRequests > 0) {
      blockedUsers.add(userId);
    }
  }

  return {
    activeUsers: activeUsers.size,
    blockedUsers: blockedUsers.size,
    totalRequests,
    totalBlocked,
    blockRate: totalRequests > 0 ? totalBlocked / totalRequests : 0,
    suspiciousUsers: suspiciousActivity.size,
    timestamp: new Date().toISOString()
  };
}

/**
 * Get user-specific rate limit status
 */
function getUserRateLimitStatus(userId) {
  const userLimits = {};
  const userHistory = userRequestHistory.get(userId);
  const suspicious = suspiciousActivity.get(userId) || [];

  // Collect all rate limits for this user
  for (const [key, data] of userRateLimits.entries()) {
    if (key.startsWith(userId + ':')) {
      const category = key.split(':')[1];
      userLimits[category] = {
        totalRequests: data.totalRequests,
        blockedRequests: data.blockedRequests,
        currentRequests: data.requests.length,
        lastRequest: new Date(data.lastRequest).toISOString()
      };
    }
  }

  return {
    userId: userId.substring(0, 8) + '...', // Masked for privacy
    limits: userLimits,
    activity: userHistory ? {
      recentRequestCount: userHistory.requests.length,
      uniqueEndpoints: userHistory.endpoints.size,
      lastActivity: new Date(userHistory.lastActivity).toISOString()
    } : null,
    suspicious: suspicious.length > 0 ? {
      count: suspicious.length,
      types: [...new Set(suspicious.map(s => s.type))]
    } : null
  };
}

// Periodic cleanup of old data
setInterval(() => {
  const now = Date.now();
  const oneHourAgo = now - (60 * 60 * 1000);
  
  // Clean up old rate limit data
  for (const [key, data] of userRateLimits.entries()) {
    if (data.lastRequest && data.lastRequest < oneHourAgo) {
      userRateLimits.delete(key);
    }
  }
  
  // Clean up old request history
  for (const [key, data] of userRequestHistory.entries()) {
    if (data.lastActivity < oneHourAgo) {
      userRequestHistory.delete(key);
    }
  }
  
  console.log(`🧹 Rate limit cleanup: ${userRateLimits.size} active limits, ${userRequestHistory.size} active users`);
}, 10 * 60 * 1000); // Every 10 minutes

module.exports = {
  createUserRateLimit,
  getRateLimitStats,
  getUserRateLimitStatus
};