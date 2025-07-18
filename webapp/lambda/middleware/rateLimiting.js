/**
 * Advanced Rate Limiting and Abuse Prevention Middleware
 * Multi-tier rate limiting with intelligent threat detection
 */

class RateLimitingMiddleware {
    constructor() {
        // In-memory store for rate limiting (in production, use Redis)
        this.requestStore = new Map();
        this.blacklistedIPs = new Set();
        this.suspiciousIPs = new Map();
        
        // Rate limiting tiers
        this.limits = {
            auth: {
                windowMs: 15 * 60 * 1000, // 15 minutes
                maxRequests: 5,
                blockDuration: 60 * 60 * 1000 // 1 hour
            },
            api: {
                windowMs: 60 * 1000, // 1 minute
                maxRequests: 100,
                blockDuration: 5 * 60 * 1000 // 5 minutes
            },
            trading: {
                windowMs: 60 * 1000, // 1 minute
                maxRequests: 30,
                blockDuration: 10 * 60 * 1000 // 10 minutes
            },
            search: {
                windowMs: 60 * 1000, // 1 minute
                maxRequests: 50,
                blockDuration: 2 * 60 * 1000 // 2 minutes
            },
            upload: {
                windowMs: 60 * 1000, // 1 minute
                maxRequests: 5,
                blockDuration: 30 * 60 * 1000 // 30 minutes
            }
        };

        // Cleanup interval
        setInterval(() => this.cleanup(), 5 * 60 * 1000); // Every 5 minutes
    }

    /**
     * Get client identifier (IP + User-Agent hash for better tracking)
     */
    getClientId(req) {
        const ip = req.ip || req.connection.remoteAddress || req.headers['x-forwarded-for'];
        const userAgent = req.get('User-Agent') || 'unknown';
        const userId = req.user?.id || req.userId || 'anonymous';
        
        // Create composite identifier
        return `${ip}:${this.hashString(userAgent)}:${userId}`;
    }

    /**
     * Simple string hash function
     */
    hashString(str) {
        let hash = 0;
        for (let i = 0; i < str.length; i++) {
            const char = str.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash & hash; // Convert to 32bit integer
        }
        return Math.abs(hash).toString(36);
    }

    /**
     * Check if IP is blacklisted
     */
    isBlacklisted(req) {
        const ip = req.ip || req.connection.remoteAddress;
        return this.blacklistedIPs.has(ip);
    }

    /**
     * Add IP to blacklist
     */
    blacklistIP(ip, reason = 'abuse_detected', duration = 24 * 60 * 60 * 1000) {
        console.warn(`🚨 Blacklisting IP ${ip} for ${reason}`);
        this.blacklistedIPs.add(ip);
        
        // Auto-remove after duration
        setTimeout(() => {
            this.blacklistedIPs.delete(ip);
            console.log(`✅ Removed IP ${ip} from blacklist`);
        }, duration);
    }

    /**
     * Track suspicious activity
     */
    trackSuspiciousActivity(req, reason) {
        const ip = req.ip || req.connection.remoteAddress;
        const currentTime = Date.now();
        
        if (!this.suspiciousIPs.has(ip)) {
            this.suspiciousIPs.set(ip, {
                count: 0,
                firstSeen: currentTime,
                lastSeen: currentTime,
                reasons: []
            });
        }

        const suspicious = this.suspiciousIPs.get(ip);
        suspicious.count++;
        suspicious.lastSeen = currentTime;
        suspicious.reasons.push({ reason, timestamp: currentTime });

        // Keep only recent reasons (last hour)
        const oneHourAgo = currentTime - (60 * 60 * 1000);
        suspicious.reasons = suspicious.reasons.filter(r => r.timestamp > oneHourAgo);

        // Auto-blacklist if too many suspicious activities
        if (suspicious.count >= 10) {
            this.blacklistIP(ip, 'repeated_suspicious_activity');
            this.suspiciousIPs.delete(ip);
        }

        console.warn(`⚠️ Suspicious activity from ${ip}: ${reason} (count: ${suspicious.count})`);
    }

    /**
     * Rate limiting logic
     */
    rateLimit(category = 'api') {
        return (req, res, next) => {
            // Check blacklist first
            if (this.isBlacklisted(req)) {
                console.warn(`🚫 Blocked request from blacklisted IP: ${req.ip}`);
                return res.status(429).json({
                    success: false,
                    error: 'Access denied',
                    code: 'IP_BLACKLISTED',
                    retryAfter: 3600
                });
            }

            const clientId = this.getClientId(req);
            const limit = this.limits[category];
            const currentTime = Date.now();
            const key = `${category}:${clientId}`;

            // Get or create request record
            let record = this.requestStore.get(key);
            if (!record) {
                record = {
                    count: 0,
                    resetTime: currentTime + limit.windowMs,
                    blockedUntil: 0
                };
                this.requestStore.set(key, record);
            }

            // Check if currently blocked
            if (record.blockedUntil > currentTime) {
                const remainingTime = Math.ceil((record.blockedUntil - currentTime) / 1000);
                console.warn(`🚫 Rate limit block active for ${clientId} in ${category} (${remainingTime}s remaining)`);
                
                this.trackSuspiciousActivity(req, 'rate_limit_violation');
                
                return res.status(429).json({
                    success: false,
                    error: 'Rate limit exceeded',
                    code: 'RATE_LIMITED',
                    retryAfter: remainingTime,
                    category
                });
            }

            // Reset window if expired
            if (currentTime > record.resetTime) {
                record.count = 0;
                record.resetTime = currentTime + limit.windowMs;
            }

            // Increment request count
            record.count++;

            // Check if limit exceeded
            if (record.count > limit.maxRequests) {
                record.blockedUntil = currentTime + limit.blockDuration;
                const blockDurationSeconds = Math.ceil(limit.blockDuration / 1000);
                
                console.warn(`🚨 Rate limit exceeded for ${clientId} in ${category}. Blocked for ${blockDurationSeconds}s`);
                
                this.trackSuspiciousActivity(req, 'rate_limit_exceeded');

                return res.status(429).json({
                    success: false,
                    error: 'Rate limit exceeded',
                    code: 'RATE_LIMITED',
                    retryAfter: blockDurationSeconds,
                    category
                });
            }

            // Add rate limit headers
            const remaining = limit.maxRequests - record.count;
            const resetTime = Math.ceil((record.resetTime - currentTime) / 1000);

            res.setHeader('X-RateLimit-Limit', limit.maxRequests);
            res.setHeader('X-RateLimit-Remaining', remaining);
            res.setHeader('X-RateLimit-Reset', resetTime);
            res.setHeader('X-RateLimit-Category', category);

            // Warning when approaching limit
            if (remaining <= 5) {
                console.warn(`⚠️ Client ${clientId} approaching rate limit in ${category}: ${remaining} requests remaining`);
            }

            next();
        };
    }

    /**
     * Adaptive rate limiting based on endpoint sensitivity
     */
    adaptiveRateLimit() {
        return (req, res, next) => {
            // Determine category based on endpoint
            let category = 'api';
            
            if (req.path.includes('/auth') || req.path.includes('/login')) {
                category = 'auth';
            } else if (req.path.includes('/trade') || req.path.includes('/order')) {
                category = 'trading';
            } else if (req.path.includes('/search')) {
                category = 'search';
            } else if (req.method === 'POST' && req.path.includes('/upload')) {
                category = 'upload';
            }

            this.rateLimit(category)(req, res, next);
        };
    }

    /**
     * Detect and prevent abuse patterns
     */
    abuseDetection() {
        return (req, res, next) => {
            const clientId = this.getClientId(req);
            const currentTime = Date.now();
            const abuseKey = `abuse:${clientId}`;

            // Track request patterns
            let abuseRecord = this.requestStore.get(abuseKey);
            if (!abuseRecord) {
                abuseRecord = {
                    requestTimes: [],
                    distinctEndpoints: new Set(),
                    httpMethods: new Set(),
                    userAgents: new Set(),
                    suspiciousHeaders: 0
                };
                this.requestStore.set(abuseKey, abuseRecord);
            }

            // Add current request
            abuseRecord.requestTimes.push(currentTime);
            abuseRecord.distinctEndpoints.add(req.path);
            abuseRecord.httpMethods.add(req.method);
            abuseRecord.userAgents.add(req.get('User-Agent') || 'unknown');

            // Keep only recent requests (last 10 minutes)
            const tenMinutesAgo = currentTime - (10 * 60 * 1000);
            abuseRecord.requestTimes = abuseRecord.requestTimes.filter(time => time > tenMinutesAgo);

            // Abuse detection patterns
            const recentRequests = abuseRecord.requestTimes.length;
            const distinctEndpoints = abuseRecord.distinctEndpoints.size;
            const distinctMethods = abuseRecord.httpMethods.size;
            const distinctUserAgents = abuseRecord.userAgents.size;

            // Pattern 1: Too many requests in short time
            if (recentRequests > 200) {
                this.trackSuspiciousActivity(req, 'high_request_volume');
            }

            // Pattern 2: Scanning behavior (many different endpoints)
            if (distinctEndpoints > 50) {
                this.trackSuspiciousActivity(req, 'endpoint_scanning');
            }

            // Pattern 3: Multiple user agents (bot detection)
            if (distinctUserAgents > 5) {
                this.trackSuspiciousActivity(req, 'multiple_user_agents');
            }

            // Pattern 4: Suspicious headers
            const suspiciousHeaders = [
                'x-forwarded-for',
                'x-real-ip',
                'x-originating-ip',
                'x-remote-ip'
            ];

            let headerCount = 0;
            for (const header of suspiciousHeaders) {
                if (req.headers[header]) {
                    headerCount++;
                }
            }

            if (headerCount > 2) {
                this.trackSuspiciousActivity(req, 'suspicious_headers');
            }

            // Pattern 5: Rapid sequential requests (< 100ms apart)
            if (abuseRecord.requestTimes.length >= 2) {
                const lastRequest = abuseRecord.requestTimes[abuseRecord.requestTimes.length - 1];
                const secondLastRequest = abuseRecord.requestTimes[abuseRecord.requestTimes.length - 2];
                
                if (lastRequest - secondLastRequest < 100) {
                    this.trackSuspiciousActivity(req, 'rapid_requests');
                }
            }

            next();
        };
    }

    /**
     * Cleanup old records
     */
    cleanup() {
        const currentTime = Date.now();
        let cleanedCount = 0;

        for (const [key, record] of this.requestStore.entries()) {
            // Remove old rate limit records
            if (record.resetTime && record.resetTime < currentTime - (60 * 60 * 1000)) {
                this.requestStore.delete(key);
                cleanedCount++;
            }
            // Remove old abuse records
            else if (record.requestTimes && record.requestTimes.length === 0) {
                this.requestStore.delete(key);
                cleanedCount++;
            }
        }

        // Clean up old suspicious IP records
        const oneHourAgo = currentTime - (60 * 60 * 1000);
        for (const [ip, record] of this.suspiciousIPs.entries()) {
            if (record.lastSeen < oneHourAgo) {
                this.suspiciousIPs.delete(ip);
                cleanedCount++;
            }
        }

        if (cleanedCount > 0) {
            console.log(`🧹 Cleaned up ${cleanedCount} old rate limiting records`);
        }
    }

    /**
     * Get rate limiting statistics
     */
    getStats() {
        const currentTime = Date.now();
        const stats = {
            totalRecords: this.requestStore.size,
            blacklistedIPs: this.blacklistedIPs.size,
            suspiciousIPs: this.suspiciousIPs.size,
            activeBlocks: 0,
            categories: {}
        };

        // Count active blocks by category
        for (const [key, record] of this.requestStore.entries()) {
            if (record.blockedUntil > currentTime) {
                stats.activeBlocks++;
                const category = key.split(':')[0];
                stats.categories[category] = (stats.categories[category] || 0) + 1;
            }
        }

        return stats;
    }

    /**
     * Manual IP management
     */
    unblacklistIP(ip) {
        this.blacklistedIPs.delete(ip);
        this.suspiciousIPs.delete(ip);
        console.log(`✅ Manually removed IP ${ip} from blacklist`);
    }

    clearRateLimit(clientId, category = null) {
        if (category) {
            const key = `${category}:${clientId}`;
            this.requestStore.delete(key);
        } else {
            // Clear all categories for this client
            for (const key of this.requestStore.keys()) {
                if (key.includes(clientId)) {
                    this.requestStore.delete(key);
                }
            }
        }
        console.log(`✅ Cleared rate limits for client ${clientId} in ${category || 'all categories'}`);
    }
}

module.exports = RateLimitingMiddleware;