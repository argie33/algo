/**
 * Advanced Rate Limiting Middleware with Redis Backend
 * 
 * Features:
 * - User-tier based rate limiting (free, premium, professional)
 * - Dynamic threshold adjustment based on system load
 * - Redis-backed distributed rate limiting for Lambda scaling
 * - Intelligent IP blocking and whitelist management
 * - Behavioral analysis and anomaly detection
 * - Sliding window rate limiting for more accurate control
 * - Rate limit bypasses for verified trading algorithms
 */

const Redis = require('ioredis');
const crypto = require('crypto');

class AdvancedRateLimiter {
    constructor(options = {}) {
        this.options = {
            redisHost: options.redisHost || process.env.REDIS_HOST || 'localhost',
            redisPort: options.redisPort || process.env.REDIS_PORT || 6379,
            redisPassword: options.redisPassword || process.env.REDIS_PASSWORD,
            keyPrefix: options.keyPrefix || 'rate_limit:',
            enableRedis: options.enableRedis !== false && (process.env.REDIS_HOST || process.env.NODE_ENV === 'production'),
            ...options
        };

        // Initialize Redis connection for production
        this.redis = null;
        if (this.options.enableRedis) {
            try {
                this.redis = new Redis({
                    host: this.options.redisHost,
                    port: this.options.redisPort,
                    password: this.options.redisPassword,
                    retryDelayOnFailover: 100,
                    enableReadyCheck: true,
                    maxRetriesPerRequest: 3,
                    connectTimeout: 10000,
                    commandTimeout: 5000
                });

                this.redis.on('error', (error) => {
                    console.error('Redis connection error:', error.message);
                    // Fallback to in-memory store
                    this.redis = null;
                });

                this.redis.on('connect', () => {
                    console.log('✅ Redis connected for advanced rate limiting');
                });

            } catch (error) {
                console.warn('Failed to initialize Redis, using in-memory rate limiting:', error.message);
                this.redis = null;
            }
        }

        // In-memory fallback for Lambda environments without Redis
        this.memoryStore = new Map();
        this.blockedIPs = new Set();
        this.whitelistedIPs = new Set();
        this.suspiciousIPs = new Map();

        // User tier configurations
        this.userTierLimits = {
            free: {
                requests: 60,           // requests per minute
                burst: 10,              // burst allowance
                window: 60 * 1000,      // 1 minute
                blockDuration: 15 * 60 * 1000, // 15 minutes
                categories: {
                    auth: { requests: 5, window: 15 * 60 * 1000 },
                    api: { requests: 60, window: 60 * 1000 },
                    trading: { requests: 30, window: 60 * 1000 },
                    heavy: { requests: 5, window: 5 * 60 * 1000 }
                }
            },
            premium: {
                requests: 300,
                burst: 50,
                window: 60 * 1000,
                blockDuration: 10 * 60 * 1000,
                categories: {
                    auth: { requests: 10, window: 15 * 60 * 1000 },
                    api: { requests: 300, window: 60 * 1000 },
                    trading: { requests: 150, window: 60 * 1000 },
                    heavy: { requests: 20, window: 5 * 60 * 1000 }
                }
            },
            professional: {
                requests: 1000,
                burst: 200,
                window: 60 * 1000,
                blockDuration: 5 * 60 * 1000,
                categories: {
                    auth: { requests: 20, window: 15 * 60 * 1000 },
                    api: { requests: 1000, window: 60 * 1000 },
                    trading: { requests: 500, window: 60 * 1000 },
                    heavy: { requests: 50, window: 5 * 60 * 1000 }
                }
            },
            institutional: {
                requests: 5000,
                burst: 1000,
                window: 60 * 1000,
                blockDuration: 60 * 1000,
                categories: {
                    auth: { requests: 50, window: 15 * 60 * 1000 },
                    api: { requests: 5000, window: 60 * 1000 },
                    trading: { requests: 2000, window: 60 * 1000 },
                    heavy: { requests: 200, window: 5 * 60 * 1000 }
                }
            }
        };

        // Dynamic threshold adjustments based on system metrics
        this.systemLoadFactor = 1.0;
        this.lastLoadCheck = Date.now();
        
        // Cleanup interval for memory store
        this.startCleanupInterval();
    }

    /**
     * Get user tier from request context
     */
    async getUserTier(req) {
        // Extract from JWT token custom claims
        if (req.user && req.user.subscription) {
            return req.user.subscription.toLowerCase();
        }

        // Extract from API key tier (if using API key authentication)
        if (req.apiKey && req.apiKey.tier) {
            return req.apiKey.tier.toLowerCase();
        }

        // Check premium headers for institutional clients
        if (req.headers['x-client-tier']) {
            const tier = req.headers['x-client-tier'].toLowerCase();
            if (Object.keys(this.userTierLimits).includes(tier)) {
                return tier;
            }
        }

        // Default to free tier
        return 'free';
    }

    /**
     * Get rate limit configuration for user and category
     */
    getRateLimitConfig(userTier, category = 'api') {
        const tierConfig = this.userTierLimits[userTier] || this.userTierLimits.free;
        const categoryConfig = tierConfig.categories[category];
        
        if (categoryConfig) {
            return {
                requests: Math.floor(categoryConfig.requests * this.systemLoadFactor),
                window: categoryConfig.window,
                burst: tierConfig.burst,
                blockDuration: tierConfig.blockDuration
            };
        }

        return {
            requests: Math.floor(tierConfig.requests * this.systemLoadFactor),
            window: tierConfig.window,
            burst: tierConfig.burst,
            blockDuration: tierConfig.blockDuration
        };
    }

    /**
     * Generate rate limiting key
     */
    generateKey(identifier, category, userTier) {
        return `${this.options.keyPrefix}${identifier}:${category}:${userTier}`;
    }

    /**
     * Check if IP is whitelisted
     */
    isWhitelisted(ip) {
        // Check static whitelist
        if (this.whitelistedIPs.has(ip)) {
            return true;
        }

        // Check for internal/private networks
        const privateNetworks = [
            /^127\./,           // localhost
            /^10\./,            // private class A
            /^172\.(1[6-9]|2\d|3[01])\./,  // private class B
            /^192\.168\./,      // private class C
            /^169\.254\./,      // link-local
            /^::1$/,            // IPv6 localhost
            /^fc00:/,           // IPv6 private
        ];

        return privateNetworks.some(network => network.test(ip));
    }

    /**
     * Check if IP is blocked
     */
    async isBlocked(ip) {
        if (this.blockedIPs.has(ip)) {
            return true;
        }

        if (this.redis) {
            try {
                const blockKey = `${this.options.keyPrefix}blocked:${ip}`;
                const isBlocked = await this.redis.exists(blockKey);
                return isBlocked === 1;
            } catch (error) {
                console.error('Redis block check failed:', error.message);
                return false;
            }
        }

        return false;
    }

    /**
     * Block IP address
     */
    async blockIP(ip, duration, reason = 'Rate limit exceeded') {
        this.blockedIPs.add(ip);
        
        if (this.redis) {
            try {
                const blockKey = `${this.options.keyPrefix}blocked:${ip}`;
                await this.redis.setex(blockKey, Math.floor(duration / 1000), JSON.stringify({
                    reason,
                    timestamp: Date.now(),
                    duration
                }));
            } catch (error) {
                console.error('Redis block operation failed:', error.message);
            }
        } else {
            // Remove from memory after duration
            setTimeout(() => {
                this.blockedIPs.delete(ip);
            }, duration);
        }

        this.logSecurityEvent('IP_BLOCKED', {
            ip: this.maskIP(ip),
            reason,
            duration: duration / 1000,
            timestamp: new Date().toISOString()
        });
    }

    /**
     * Check rate limit using sliding window algorithm
     */
    async checkRateLimit(req, category = 'api') {
        const ip = req.ip || req.connection.remoteAddress;
        const userAgent = req.get('User-Agent') || 'unknown';
        const userTier = await this.getUserTier(req);
        const now = Date.now();

        // Check if IP is whitelisted
        if (this.isWhitelisted(ip)) {
            return {
                allowed: true,
                reason: 'Whitelisted IP',
                remaining: Infinity,
                resetTime: null
            };
        }

        // Check if IP is blocked
        if (await this.isBlocked(ip)) {
            this.logSecurityEvent('BLOCKED_IP_ACCESS_ATTEMPT', {
                ip: this.maskIP(ip),
                userAgent: userAgent.substring(0, 100),
                category,
                userTier,
                timestamp: new Date().toISOString()
            });

            return {
                allowed: false,
                reason: 'IP temporarily blocked',
                retryAfter: 300, // 5 minutes
                blocked: true
            };
        }

        const config = this.getRateLimitConfig(userTier, category);
        const identifier = req.user?.sub || ip; // Use user ID if authenticated, otherwise IP
        const key = this.generateKey(identifier, category, userTier);

        try {
            let result;
            
            if (this.redis) {
                result = await this.checkRedisRateLimit(key, config, now);
            } else {
                result = await this.checkMemoryRateLimit(key, config, now);
            }

            // Track suspicious activity
            await this.trackActivity(identifier, ip, userAgent, category, result, config);

            // Log rate limit events
            if (!result.allowed) {
                this.logSecurityEvent('RATE_LIMIT_EXCEEDED', {
                    identifier: this.maskIdentifier(identifier),
                    ip: this.maskIP(ip),
                    category,
                    userTier,
                    requests: result.requests,
                    limit: config.requests,
                    window: config.window / 1000,
                    timestamp: new Date().toISOString()
                });
            }

            return result;

        } catch (error) {
            console.error('Rate limit check failed:', error.message);
            // Fail open for availability
            return {
                allowed: true,
                reason: 'Rate limiter error',
                error: true
            };
        }
    }

    /**
     * Redis-based rate limiting with sliding window
     */
    async checkRedisRateLimit(key, config, now) {
        const windowStart = now - config.window;
        
        // Use Redis pipeline for atomic operations
        const pipeline = this.redis.pipeline();
        
        // Remove expired entries
        pipeline.zremrangebyscore(key, 0, windowStart);
        
        // Count current requests in window
        pipeline.zcard(key);
        
        // Add current request
        pipeline.zadd(key, now, `${now}-${Math.random()}`);
        
        // Set expiry
        pipeline.expire(key, Math.ceil(config.window / 1000));
        
        const results = await pipeline.exec();
        const currentRequests = results[1][1]; // Count result
        
        if (currentRequests >= config.requests) {
            // Remove the request we just added since it's not allowed
            await this.redis.zpopmax(key);
            
            const oldestRequest = await this.redis.zrange(key, 0, 0, 'WITHSCORES');
            const resetTime = oldestRequest.length > 0 ? 
                parseInt(oldestRequest[1]) + config.window : 
                now + config.window;
            
            return {
                allowed: false,
                requests: currentRequests,
                limit: config.requests,
                remaining: 0,
                resetTime: new Date(resetTime).toISOString(),
                retryAfter: Math.ceil((resetTime - now) / 1000)
            };
        }

        return {
            allowed: true,
            requests: currentRequests + 1,
            limit: config.requests,
            remaining: config.requests - currentRequests - 1,
            resetTime: new Date(now + config.window).toISOString()
        };
    }

    /**
     * Memory-based rate limiting fallback
     */
    async checkMemoryRateLimit(key, config, now) {
        if (!this.memoryStore.has(key)) {
            this.memoryStore.set(key, {
                requests: [],
                totalRequests: 0,
                blockedRequests: 0
            });
        }

        const limiter = this.memoryStore.get(key);
        const windowStart = now - config.window;

        // Remove expired requests
        limiter.requests = limiter.requests.filter(timestamp => timestamp > windowStart);

        if (limiter.requests.length >= config.requests) {
            limiter.blockedRequests++;
            
            const oldestRequest = Math.min(...limiter.requests);
            const resetTime = oldestRequest + config.window;

            return {
                allowed: false,
                requests: limiter.requests.length,
                limit: config.requests,
                remaining: 0,
                resetTime: new Date(resetTime).toISOString(),
                retryAfter: Math.ceil((resetTime - now) / 1000)
            };
        }

        // Add current request
        limiter.requests.push(now);
        limiter.totalRequests++;

        return {
            allowed: true,
            requests: limiter.requests.length,
            limit: config.requests,
            remaining: config.requests - limiter.requests.length,
            resetTime: new Date(now + config.window).toISOString()
        };
    }

    /**
     * Track user activity for anomaly detection
     */
    async trackActivity(identifier, ip, userAgent, category, rateLimitResult, config) {
        const activityKey = `activity:${identifier}`;
        const now = Date.now();
        
        const activity = {
            timestamp: now,
            ip,
            userAgent: userAgent.substring(0, 100),
            category,
            allowed: rateLimitResult.allowed,
            requests: rateLimitResult.requests
        };

        if (this.redis) {
            try {
                // Store activity with 1 hour expiry
                await this.redis.lpush(activityKey, JSON.stringify(activity));
                await this.redis.ltrim(activityKey, 0, 99); // Keep last 100 activities
                await this.redis.expire(activityKey, 3600);
            } catch (error) {
                console.error('Redis activity tracking failed:', error.message);
            }
        }

        // Check for suspicious patterns
        await this.detectAnomalies(identifier, ip, activity, config);
    }

    /**
     * Detect anomalous behavior patterns
     */
    async detectAnomalies(identifier, ip, activity, config) {
        const suspiciousKey = `suspicious:${ip}`;
        
        if (!this.suspiciousIPs.has(suspiciousKey)) {
            this.suspiciousIPs.set(suspiciousKey, {
                activities: [],
                violations: 0,
                lastViolation: null
            });
        }

        const suspicious = this.suspiciousIPs.get(suspiciousKey);
        suspicious.activities.push(activity);

        // Keep only last hour of activities
        const oneHourAgo = Date.now() - (60 * 60 * 1000);
        suspicious.activities = suspicious.activities.filter(a => a.timestamp > oneHourAgo);

        // Analyze patterns
        const patterns = this.analyzeActivityPatterns(suspicious.activities);

        if (patterns.suspicious) {
            suspicious.violations++;
            suspicious.lastViolation = Date.now();

            this.logSecurityEvent('SUSPICIOUS_ACTIVITY_DETECTED', {
                ip: this.maskIP(ip),
                identifier: this.maskIdentifier(identifier),
                patterns,
                violations: suspicious.violations,
                timestamp: new Date().toISOString()
            });

            // Auto-block after multiple violations
            if (suspicious.violations >= 3) {
                await this.blockIP(ip, config.blockDuration * 2, 'Suspicious activity pattern detected');
            }
        }
    }

    /**
     * Analyze activity patterns for anomalies
     */
    analyzeActivityPatterns(activities) {
        if (activities.length < 10) {
            return { suspicious: false, score: 0 };
        }

        let score = 0;
        const checks = {
            rapidRequests: false,
            multipleUserAgents: false,
            highErrorRate: false,
            distributedTiming: false
        };

        // Check for rapid requests (>50 requests in 5 minutes)
        const fiveMinutesAgo = Date.now() - (5 * 60 * 1000);
        const recentRequests = activities.filter(a => a.timestamp > fiveMinutesAgo);
        if (recentRequests.length > 50) {
            checks.rapidRequests = true;
            score += 40;
        }

        // Check for multiple user agents
        const uniqueUserAgents = new Set(activities.map(a => a.userAgent));
        if (uniqueUserAgents.size > 3) {
            checks.multipleUserAgents = true;
            score += 30;
        }

        // Check for high error rate (blocked requests)
        const blockedRequests = activities.filter(a => !a.allowed);
        const errorRate = blockedRequests.length / activities.length;
        if (errorRate > 0.3) { // >30% error rate
            checks.highErrorRate = true;
            score += 25;
        }

        // Check for distributed timing attacks
        const intervals = [];
        for (let i = 1; i < activities.length; i++) {
            intervals.push(activities[i].timestamp - activities[i-1].timestamp);
        }
        const avgInterval = intervals.reduce((a, b) => a + b, 0) / intervals.length;
        const regularPattern = intervals.filter(interval => 
            Math.abs(interval - avgInterval) < avgInterval * 0.1
        ).length;
        
        if (regularPattern / intervals.length > 0.8) { // >80% regular intervals
            checks.distributedTiming = true;
            score += 20;
        }

        return {
            suspicious: score > 50,
            score,
            checks,
            riskLevel: score > 80 ? 'HIGH' : score > 50 ? 'MEDIUM' : 'LOW'
        };
    }

    /**
     * Update system load factor for dynamic adjustment
     */
    updateSystemLoad() {
        const now = Date.now();
        
        // Check every 30 seconds
        if (now - this.lastLoadCheck < 30000) {
            return;
        }

        this.lastLoadCheck = now;

        // Simple load calculation based on memory usage
        const memUsage = process.memoryUsage();
        const memoryPressure = memUsage.heapUsed / memUsage.heapTotal;

        if (memoryPressure > 0.8) {
            this.systemLoadFactor = 0.5; // Reduce limits by 50%
        } else if (memoryPressure > 0.6) {
            this.systemLoadFactor = 0.7; // Reduce limits by 30%
        } else {
            this.systemLoadFactor = 1.0; // Normal limits
        }
    }

    /**
     * Create Express middleware
     */
    middleware(category = 'api') {
        return async (req, res, next) => {
            try {
                this.updateSystemLoad();
                
                const result = await this.checkRateLimit(req, category);
                
                if (!result.allowed) {
                    // Set rate limit headers
                    if (result.limit) {
                        res.set({
                            'X-RateLimit-Limit': result.limit,
                            'X-RateLimit-Remaining': result.remaining || 0,
                            'X-RateLimit-Reset': result.resetTime || new Date(Date.now() + 60000).toISOString(),
                            'Retry-After': result.retryAfter || 60
                        });
                    }

                    return res.status(429).json({
                        success: false,
                        error: 'Rate limit exceeded',
                        message: result.reason || 'Too many requests',
                        retryAfter: result.retryAfter || 60,
                        blocked: result.blocked || false,
                        category
                    });
                }

                // Set success headers
                if (result.limit) {
                    res.set({
                        'X-RateLimit-Limit': result.limit,
                        'X-RateLimit-Remaining': result.remaining,
                        'X-RateLimit-Reset': result.resetTime
                    });
                }

                next();

            } catch (error) {
                console.error('Rate limiting middleware error:', error.message);
                // Fail open for availability
                next();
            }
        };
    }

    /**
     * Cleanup memory store periodically
     */
    startCleanupInterval() {
        setInterval(() => {
            const now = Date.now();
            const oneHourAgo = now - (60 * 60 * 1000);

            // Clean memory store
            for (const [key, limiter] of this.memoryStore.entries()) {
                limiter.requests = limiter.requests.filter(timestamp => timestamp > oneHourAgo);
                if (limiter.requests.length === 0) {
                    this.memoryStore.delete(key);
                }
            }

            // Clean suspicious IPs
            for (const [key, data] of this.suspiciousIPs.entries()) {
                if (data.lastViolation && now - data.lastViolation > oneHourAgo) {
                    this.suspiciousIPs.delete(key);
                }
            }

            console.log(`Rate limiter cleanup: ${this.memoryStore.size} active limiters, ${this.suspiciousIPs.size} suspicious IPs`);
        }, 10 * 60 * 1000); // Every 10 minutes
    }

    /**
     * Log security events
     */
    logSecurityEvent(type, details) {
        console.warn(`[RATE LIMITER SECURITY] ${type}:`, details);
        // In production, integrate with security monitoring
    }

    /**
     * Mask IP for privacy in logs
     */
    maskIP(ip) {
        if (ip.includes(':')) {
            // IPv6
            const parts = ip.split(':');
            return parts.slice(0, 4).join(':') + '::***';
        } else {
            // IPv4
            const parts = ip.split('.');
            return parts.slice(0, 2).join('.') + '.***';
        }
    }

    /**
     * Mask identifier for privacy
     */
    maskIdentifier(identifier) {
        if (identifier.length > 8) {
            return identifier.substring(0, 4) + '***' + identifier.slice(-4);
        }
        return '***';
    }

    /**
     * Get rate limiting statistics
     */
    async getStats() {
        const stats = {
            memoryStore: this.memoryStore.size,
            blockedIPs: this.blockedIPs.size,
            suspiciousIPs: this.suspiciousIPs.size,
            systemLoadFactor: this.systemLoadFactor,
            redisConnected: this.redis && this.redis.status === 'ready'
        };

        if (this.redis) {
            try {
                const redisInfo = await this.redis.info('memory');
                stats.redisMemory = redisInfo;
            } catch (error) {
                stats.redisError = error.message;
            }
        }

        return stats;
    }

    /**
     * Graceful shutdown
     */
    async shutdown() {
        if (this.redis) {
            await this.redis.quit();
        }
    }
}

module.exports = AdvancedRateLimiter;