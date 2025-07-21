/**
 * Enhanced Authentication and Authorization Middleware
 * Advanced security features for financial trading platform
 * Integrates with EnhancedAuthService for comprehensive security
 */

const jwt = require('jsonwebtoken');
const crypto = require('crypto');
const EnhancedAuthService = require('../services/enhancedAuthService');
const logger = require('../utils/logger');

class EnhancedAuthMiddleware {
    constructor() {
        this.authService = new EnhancedAuthService();
        this.jwtSecret = process.env.JWT_SECRET || 'fallback-secret-change-in-production';
        this.sessionStore = new Map(); // In production, use Redis
        this.failedAttempts = new Map();
        this.deviceFingerprints = new Map();
        this.rateLimitStore = new Map();
        this.suspiciousActivityStore = new Map();
        
        // Security settings
        this.maxFailedAttempts = 5;
        this.lockoutDuration = 30 * 60 * 1000; // 30 minutes
        this.sessionTimeout = 24 * 60 * 60 * 1000; // 24 hours
        this.deviceTrustDuration = 7 * 24 * 60 * 60 * 1000; // 7 days
        
        // Rate limiting configuration
        this.config = {
            rateLimit: {
                windowMs: 15 * 60 * 1000, // 15 minutes
                maxRequests: 100,
                blockDuration: 60 * 60 * 1000, // 1 hour
                strictPaths: ['/api/auth/login', '/api/auth/register'],
                strictLimit: 5
            },
            session: {
                maxAge: 24 * 60 * 60 * 1000, // 24 hours
                renewThreshold: 30 * 60 * 1000, // 30 minutes before expiry
                maxConcurrent: 3
            },
            security: {
                maxLoginAttempts: 5,
                lockoutDuration: 30 * 60 * 1000, // 30 minutes
                suspiciousThreshold: 10,
                ipWhitelist: process.env.IP_WHITELIST?.split(',') || [],
                trustedProxies: process.env.TRUSTED_PROXIES?.split(',') || []
            },
            cors: {
                allowedOrigins: process.env.ALLOWED_ORIGINS?.split(',') || ['https://d1zb7knau41vl9.cloudfront.net'],
                allowedMethods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
                allowedHeaders: ['Content-Type', 'Authorization', 'X-Requested-With', 'X-API-Key', 'X-Session-ID'],
                exposedHeaders: ['X-Rate-Limit-Remaining', 'X-Rate-Limit-Reset'],
                credentials: true,
                maxAge: 86400 // 24 hours
            }
        };
        
        // Cleanup interval
        setInterval(() => this.cleanup(), 10 * 60 * 1000); // Every 10 minutes
    }

    /**
     * Generate device fingerprint from request headers
     */
    generateDeviceFingerprint(req) {
        const userAgent = req.get('User-Agent') || '';
        const acceptLanguage = req.get('Accept-Language') || '';
        const acceptEncoding = req.get('Accept-Encoding') || '';
        const ip = req.ip || req.connection.remoteAddress;
        
        const fingerprintData = `${userAgent}:${acceptLanguage}:${acceptEncoding}:${ip}`;
        return crypto.createHash('sha256').update(fingerprintData).digest('hex');
    }

    /**
     * Create secure session token
     */
    createSessionToken(userId, deviceFingerprint) {
        const sessionId = crypto.randomBytes(32).toString('hex');
        const sessionData = {
            userId,
            deviceFingerprint,
            createdAt: Date.now(),
            lastActive: Date.now(),
            ipAddress: null,
            userAgent: null
        };
        
        this.sessionStore.set(sessionId, sessionData);
        return sessionId;
    }

    /**
     * Validate session token
     */
    validateSession(sessionId, req) {
        const session = this.sessionStore.get(sessionId);
        if (!session) {
            return { valid: false, reason: 'session_not_found' };
        }

        const currentTime = Date.now();
        
        // Check session timeout
        if (currentTime - session.lastActive > this.sessionTimeout) {
            this.sessionStore.delete(sessionId);
            return { valid: false, reason: 'session_expired' };
        }

        // Check device fingerprint consistency
        const currentFingerprint = this.generateDeviceFingerprint(req);
        if (session.deviceFingerprint !== currentFingerprint) {
            console.warn(`🚨 Device fingerprint mismatch for user ${session.userId}`);
            return { valid: false, reason: 'device_mismatch' };
        }

        // Update last active time
        session.lastActive = currentTime;
        session.ipAddress = req.ip;
        session.userAgent = req.get('User-Agent');
        
        return { valid: true, session };
    }

    /**
     * Enhanced JWT token validation
     */
    validateJWT(token, req) {
        try {
            const decoded = jwt.verify(token, this.jwtSecret);
            
            // Check token age
            const tokenAge = Date.now() - (decoded.iat * 1000);
            if (tokenAge > this.sessionTimeout) {
                return { valid: false, reason: 'token_expired' };
            }

            // Check device consistency if available
            if (decoded.deviceId) {
                const currentFingerprint = this.generateDeviceFingerprint(req);
                if (decoded.deviceId !== currentFingerprint) {
                    console.warn(`🚨 JWT device mismatch for user ${decoded.userId}`);
                    return { valid: false, reason: 'device_mismatch' };
                }
            }

            return { valid: true, decoded };
        } catch (error) {
            console.warn(`🚨 JWT validation failed: ${error.message}`);
            return { valid: false, reason: 'invalid_token' };
        }
    }

    /**
     * Track failed authentication attempts
     */
    trackFailedAttempt(identifier) {
        const currentTime = Date.now();
        
        if (!this.failedAttempts.has(identifier)) {
            this.failedAttempts.set(identifier, {
                count: 0,
                firstAttempt: currentTime,
                lastAttempt: currentTime,
                lockedUntil: 0
            });
        }

        const attempts = this.failedAttempts.get(identifier);
        attempts.count++;
        attempts.lastAttempt = currentTime;

        // Apply lockout if max attempts exceeded
        if (attempts.count >= this.maxFailedAttempts) {
            attempts.lockedUntil = currentTime + this.lockoutDuration;
            console.warn(`🔒 Account locked for ${identifier} due to ${attempts.count} failed attempts`);
        }

        return attempts;
    }

    /**
     * Check if account is locked
     */
    isAccountLocked(identifier) {
        const attempts = this.failedAttempts.get(identifier);
        if (!attempts) return false;

        const currentTime = Date.now();
        if (attempts.lockedUntil > currentTime) {
            return {
                locked: true,
                remainingTime: Math.ceil((attempts.lockedUntil - currentTime) / 1000),
                attempts: attempts.count
            };
        }

        // Clear old failed attempts if lockout expired
        if (attempts.lockedUntil > 0 && attempts.lockedUntil <= currentTime) {
            this.failedAttempts.delete(identifier);
        }

        return { locked: false };
    }

    /**
     * Reset failed attempts on successful login
     */
    resetFailedAttempts(identifier) {
        this.failedAttempts.delete(identifier);
    }

    /**
     * Device trust management
     */
    trustDevice(deviceFingerprint, userId) {
        this.deviceFingerprints.set(deviceFingerprint, {
            userId,
            trustedAt: Date.now(),
            expiresAt: Date.now() + this.deviceTrustDuration
        });
        console.log(`🛡️ Device trusted for user ${userId}`);
    }

    /**
     * Check if device is trusted
     */
    isDeviceTrusted(deviceFingerprint, userId) {
        const deviceInfo = this.deviceFingerprints.get(deviceFingerprint);
        if (!deviceInfo) return false;

        if (deviceInfo.userId !== userId) return false;
        if (Date.now() > deviceInfo.expiresAt) {
            this.deviceFingerprints.delete(deviceFingerprint);
            return false;
        }

        return true;
    }

    /**
     * Enhanced main authentication middleware with comprehensive security
     */
    authenticate(options = {}) {
        return async (req, res, next) => {
            const correlationId = this.generateCorrelationId();
            req.correlationId = correlationId;
            
            try {
                // Apply security headers
                this.applySecurityHeaders(req, res);
                
                // Handle CORS
                if (this.handleCORS(req, res)) {
                    return;
                }
                
                // Get client IP
                const clientIP = this.getClientIP(req);
                req.clientIP = clientIP;
                
                // Rate limiting
                if (this.isRateLimited(req, clientIP)) {
                    return this.sendRateLimitError(res, correlationId);
                }
                
                // Check for suspicious activity
                if (this.detectSuspiciousActivity(req, clientIP)) {
                    return this.sendSuspiciousActivityError(res, correlationId);
                }
                
                // Extract and validate JWT token
                const token = this.extractToken(req);
                if (!token) {
                    if (options.required !== false) {
                        return this.sendAuthError(res, 'Authentication required', correlationId);
                    }
                    return next();
                }
                
                // Verify JWT token
                const decoded = await this.verifyToken(token, correlationId);
                if (!decoded) {
                    return this.sendAuthError(res, 'Invalid or expired token', correlationId);
                }
                
                // Get user details
                const user = await this.authService.getUserById(decoded.sub);
                if (!user || !user.isActive) {
                    return this.sendAuthError(res, 'User not found or inactive', correlationId);
                }
                
                // Validate session
                const sessionValid = await this.validateEnhancedSession(decoded, req, clientIP);
                if (!sessionValid) {
                    return this.sendAuthError(res, 'Invalid session', correlationId);
                }
                
                // Check MFA if required
                if (options.requireMFA && !decoded.mfaVerified) {
                    return this.sendMFARequired(res, correlationId);
                }
                
                // Role-based access control
                if (options.roles && !this.hasRequiredRole(user, options.roles)) {
                    return this.sendAuthError(res, 'Insufficient permissions', correlationId, 403);
                }
                
                // Permission-based access control
                if (options.permissions && !this.hasRequiredPermissions(user, options.permissions)) {
                    return this.sendAuthError(res, 'Insufficient permissions', correlationId, 403);
                }
                
                // Attach user to request
                req.user = user;
                req.token = decoded;
                req.sessionId = decoded.sessionId;
                
                // Update session activity
                this.updateSessionActivity(decoded.sessionId, req);
                
                // Log successful authentication
                logger.info('Authentication successful', {
                    correlationId,
                    userId: user.id,
                    email: user.email,
                    ip: clientIP,
                    userAgent: req.get('User-Agent'),
                    path: req.path,
                    method: req.method
                });
                
                next();
                
            } catch (error) {
                logger.error('Authentication middleware error', {
                    correlationId,
                    error: error.message,
                    stack: error.stack,
                    ip: req.clientIP,
                    path: req.path,
                    method: req.method
                });
                
                return this.sendAuthError(res, 'Authentication failed', correlationId, 500);
            }
        };
    }

    /**
     * Main authentication middleware (legacy compatibility)
     */
    requireAuth(options = {}) {
        return async (req, res, next) => {
            const { allowApiKey = true, requireSession = false, checkDevice = true } = options;
            
            try {
                let authResult = null;
                
                // Try JWT token first
                const authHeader = req.headers.authorization;
                if (authHeader && authHeader.startsWith('Bearer ')) {
                    const token = authHeader.substring(7);
                    const jwtResult = this.validateJWT(token, req);
                    
                    if (jwtResult.valid) {
                        authResult = {
                            userId: jwtResult.decoded.userId,
                            email: jwtResult.decoded.email,
                            role: jwtResult.decoded.role,
                            authMethod: 'jwt'
                        };
                    }
                }

                // Try session token
                if (!authResult && requireSession) {
                    const sessionId = req.headers['x-session-id'] || req.cookies?.sessionId;
                    if (sessionId) {
                        const sessionResult = this.validateSession(sessionId, req);
                        
                        if (sessionResult.valid) {
                            authResult = {
                                userId: sessionResult.session.userId,
                                authMethod: 'session',
                                sessionId
                            };
                        }
                    }
                }

                // Try API key authentication
                if (!authResult && allowApiKey) {
                    const apiKey = req.headers['x-api-key'];
                    if (apiKey) {
                        // Validate API key (implement your API key validation logic)
                        const apiKeyResult = await this.validateApiKey(apiKey);
                        if (apiKeyResult.valid) {
                            authResult = {
                                userId: apiKeyResult.userId,
                                authMethod: 'api_key',
                                permissions: apiKeyResult.permissions
                            };
                        }
                    }
                }

                if (!authResult) {
                    return res.status(401).json({
                        success: false,
                        error: 'Authentication required',
                        code: 'UNAUTHORIZED'
                    });
                }

                // Device check
                if (checkDevice) {
                    const deviceFingerprint = this.generateDeviceFingerprint(req);
                    const deviceTrusted = this.isDeviceTrusted(deviceFingerprint, authResult.userId);
                    
                    if (!deviceTrusted && authResult.authMethod !== 'api_key') {
                        // Log security event
                        console.warn(`🚨 Untrusted device access attempt for user ${authResult.userId}`);
                        
                        // You might want to require additional verification here
                        // For now, we'll allow but mark as untrusted
                        authResult.deviceTrusted = false;
                    } else {
                        authResult.deviceTrusted = true;
                    }
                }

                // Add auth info to request
                req.user = authResult;
                req.userId = authResult.userId;
                req.authMethod = authResult.authMethod;

                next();
                
            } catch (error) {
                console.error('🚨 Authentication error:', error);
                res.status(500).json({
                    success: false,
                    error: 'Authentication service error',
                    code: 'AUTH_ERROR'
                });
            }
        };
    }

    /**
     * Role-based authorization
     */
    requireRole(allowedRoles) {
        return (req, res, next) => {
            if (!req.user) {
                return res.status(401).json({
                    success: false,
                    error: 'Authentication required',
                    code: 'UNAUTHORIZED'
                });
            }

            const userRole = req.user.role || 'user';
            if (!allowedRoles.includes(userRole)) {
                console.warn(`🚨 Insufficient permissions for user ${req.user.userId}: required ${allowedRoles}, has ${userRole}`);
                return res.status(403).json({
                    success: false,
                    error: 'Insufficient permissions',
                    code: 'FORBIDDEN',
                    required: allowedRoles,
                    current: userRole
                });
            }

            next();
        };
    }

    /**
     * Permission-based authorization
     */
    requirePermission(permission) {
        return (req, res, next) => {
            if (!req.user) {
                return res.status(401).json({
                    success: false,
                    error: 'Authentication required',
                    code: 'UNAUTHORIZED'
                });
            }

            const userPermissions = req.user.permissions || [];
            if (!userPermissions.includes(permission)) {
                console.warn(`🚨 Missing permission for user ${req.user.userId}: required ${permission}`);
                return res.status(403).json({
                    success: false,
                    error: 'Missing required permission',
                    code: 'INSUFFICIENT_PERMISSIONS',
                    required: permission,
                    available: userPermissions
                });
            }

            next();
        };
    }

    /**
     * API key validation (stub - implement based on your system)
     */
    async validateApiKey(apiKey) {
        // Implement your API key validation logic here
        // This is a stub implementation
        try {
            // In a real implementation, you would:
            // 1. Hash the API key
            // 2. Look it up in your database
            // 3. Check if it's active and not expired
            // 4. Return user info and permissions
            
            return {
                valid: false,
                reason: 'api_key_validation_not_implemented'
            };
        } catch (error) {
            return {
                valid: false,
                reason: 'api_key_validation_error'
            };
        }
    }

    /**
     * Enhanced JWT token verification with blacklist checking
     */
    async verifyToken(token, correlationId) {
        try {
            const decoded = jwt.verify(token, this.jwtSecret);
            
            // Check if token is blacklisted
            const isBlacklisted = await this.authService.isTokenBlacklisted(token);
            if (isBlacklisted) {
                logger.warn('Blacklisted token used', {
                    correlationId,
                    tokenId: decoded.jti,
                    userId: decoded.sub
                });
                return null;
            }
            
            return decoded;
        } catch (error) {
            logger.warn('Token verification failed', {
                correlationId,
                error: error.message,
                tokenPreview: token.substring(0, 20) + '...'
            });
            return null;
        }
    }

    /**
     * Enhanced session validation with EnhancedAuthService
     */
    async validateEnhancedSession(decoded, req, clientIP) {
        const sessionId = decoded.sessionId;
        if (!sessionId) {
            return false;
        }
        
        try {
            const session = await this.authService.getSession(sessionId);
            if (!session || !session.isActive) {
                return false;
            }
            
            // Check session expiry
            if (session.expiresAt < new Date()) {
                await this.authService.invalidateSession(sessionId);
                return false;
            }
            
            // Validate IP consistency (if configured)
            if (session.ipAddress && session.ipAddress !== clientIP) {
                logger.warn('IP address mismatch for session', {
                    sessionId,
                    originalIP: session.ipAddress,
                    currentIP: clientIP,
                    userId: decoded.sub
                });
                
                // Allow IP changes for mobile users, but flag as suspicious
                this.flagSuspiciousActivity(clientIP, 'ip_change');
            }
            
            // Check concurrent sessions
            const userSessions = await this.authService.getUserActiveSessions(decoded.sub);
            if (userSessions.length > this.config.session.maxConcurrent) {
                // Invalidate oldest sessions
                const oldestSessions = userSessions
                    .sort((a, b) => a.lastActivity - b.lastActivity)
                    .slice(0, userSessions.length - this.config.session.maxConcurrent);
                
                for (const oldSession of oldestSessions) {
                    await this.authService.invalidateSession(oldSession.id);
                }
            }
            
            return true;
        } catch (error) {
            logger.error('Session validation error', {
                sessionId,
                error: error.message,
                userId: decoded.sub
            });
            return false;
        }
    }

    /**
     * Rate limiting implementation
     */
    isRateLimited(req, clientIP) {
        const key = `${clientIP}:${req.path}`;
        const now = Date.now();
        const windowMs = this.config.rateLimit.windowMs;
        
        if (!this.rateLimitStore.has(key)) {
            this.rateLimitStore.set(key, {
                requests: 1,
                resetTime: now + windowMs,
                blocked: false
            });
            return false;
        }
        
        const rateData = this.rateLimitStore.get(key);
        
        // Check if in blocked state
        if (rateData.blocked && now < rateData.blockedUntil) {
            return true;
        }
        
        // Reset window if expired
        if (now > rateData.resetTime) {
            rateData.requests = 1;
            rateData.resetTime = now + windowMs;
            rateData.blocked = false;
            return false;
        }
        
        // Increment requests
        rateData.requests++;
        
        // Check limits
        const isStrictPath = this.config.rateLimit.strictPaths.includes(req.path);
        const limit = isStrictPath ? this.config.rateLimit.strictLimit : this.config.rateLimit.maxRequests;
        
        if (rateData.requests > limit) {
            rateData.blocked = true;
            rateData.blockedUntil = now + this.config.rateLimit.blockDuration;
            
            logger.warn('Rate limit exceeded', {
                ip: clientIP,
                path: req.path,
                requests: rateData.requests,
                limit,
                userAgent: req.get('User-Agent')
            });
            
            return true;
        }
        
        return false;
    }

    /**
     * Suspicious activity detection
     */
    detectSuspiciousActivity(req, clientIP) {
        const key = `suspicious:${clientIP}`;
        const now = Date.now();
        const windowMs = 60 * 60 * 1000; // 1 hour
        
        if (!this.suspiciousActivityStore.has(key)) {
            this.suspiciousActivityStore.set(key, {
                score: 0,
                events: [],
                resetTime: now + windowMs
            });
        }
        
        const suspicious = this.suspiciousActivityStore.get(key);
        
        // Reset if window expired
        if (now > suspicious.resetTime) {
            suspicious.score = 0;
            suspicious.events = [];
            suspicious.resetTime = now + windowMs;
        }
        
        // Check for suspicious patterns
        let scoreIncrease = 0;
        
        // Multiple failed auth attempts
        if (req.path.includes('/auth/') && req.method === 'POST') {
            scoreIncrease += 2;
        }
        
        // Unusual user agent
        const userAgent = req.get('User-Agent');
        if (!userAgent || userAgent.length < 10 || /bot|crawler|spider/i.test(userAgent)) {
            scoreIncrease += 3;
        }
        
        // Rapid requests
        const recentEvents = suspicious.events.filter(event => now - event.timestamp < 60000);
        if (recentEvents.length > 20) {
            scoreIncrease += 5;
        }
        
        // Update score
        suspicious.score += scoreIncrease;
        suspicious.events.push({
            timestamp: now,
            path: req.path,
            method: req.method,
            userAgent
        });
        
        // Check threshold
        if (suspicious.score > this.config.security.suspiciousThreshold) {
            logger.warn('Suspicious activity detected', {
                ip: clientIP,
                score: suspicious.score,
                events: suspicious.events.length,
                userAgent
            });
            return true;
        }
        
        return false;
    }

    /**
     * Role-based access control
     */
    hasRequiredRole(user, requiredRoles) {
        if (!user.roles || !Array.isArray(user.roles)) {
            return false;
        }
        
        const userRoles = user.roles.map(role => role.name || role);
        return requiredRoles.some(role => userRoles.includes(role));
    }

    /**
     * Permission-based access control
     */
    hasRequiredPermissions(user, requiredPermissions) {
        if (!user.permissions || !Array.isArray(user.permissions)) {
            return false;
        }
        
        const userPermissions = user.permissions.map(perm => perm.name || perm);
        return requiredPermissions.every(permission => userPermissions.includes(permission));
    }

    /**
     * CORS handling
     */
    handleCORS(req, res) {
        const origin = req.get('Origin');
        const { allowedOrigins, allowedMethods, allowedHeaders, exposedHeaders, credentials, maxAge } = this.config.cors;
        
        // Check if origin is allowed
        if (origin && (allowedOrigins.includes('*') || allowedOrigins.includes(origin))) {
            res.header('Access-Control-Allow-Origin', origin);
        }
        
        res.header('Access-Control-Allow-Methods', allowedMethods.join(', '));
        res.header('Access-Control-Allow-Headers', allowedHeaders.join(', '));
        res.header('Access-Control-Expose-Headers', exposedHeaders.join(', '));
        res.header('Access-Control-Allow-Credentials', credentials);
        res.header('Access-Control-Max-Age', maxAge);
        
        // Handle preflight requests
        if (req.method === 'OPTIONS') {
            res.status(200).end();
            return true;
        }
        
        return false;
    }

    /**
     * Apply comprehensive security headers
     */
    applySecurityHeaders(req, res) {
        // Basic security headers
        res.header('X-Content-Type-Options', 'nosniff');
        res.header('X-Frame-Options', 'DENY');
        res.header('X-XSS-Protection', '1; mode=block');
        res.header('Referrer-Policy', 'strict-origin-when-cross-origin');
        res.header('Permissions-Policy', 'camera=(), microphone=(), geolocation=()');
        
        // Content Security Policy
        const csp = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: https:",
            "font-src 'self'",
            "connect-src 'self' https://api.alpaca.markets https://paper-api.alpaca.markets",
            "frame-src 'none'",
            "object-src 'none'",
            "base-uri 'self'"
        ].join('; ');
        
        res.header('Content-Security-Policy', csp);
        
        // HSTS (only for HTTPS)
        if (req.secure || req.get('X-Forwarded-Proto') === 'https') {
            res.header('Strict-Transport-Security', 'max-age=31536000; includeSubDomains; preload');
        }
    }

    /**
     * Utility methods
     */
    extractToken(req) {
        const authHeader = req.get('Authorization');
        if (authHeader && authHeader.startsWith('Bearer ')) {
            return authHeader.substring(7);
        }
        
        // Check for token in cookies
        const cookieToken = req.cookies?.token;
        if (cookieToken) {
            return cookieToken;
        }
        
        return null;
    }

    getClientIP(req) {
        // Check trusted proxy headers
        const forwarded = req.get('X-Forwarded-For');
        if (forwarded) {
            const ips = forwarded.split(',').map(ip => ip.trim());
            return ips[0];
        }
        
        return req.get('X-Real-IP') || 
               req.get('X-Client-IP') || 
               req.connection?.remoteAddress || 
               req.socket?.remoteAddress ||
               req.ip ||
               'unknown';
    }

    generateCorrelationId() {
        return crypto.randomUUID();
    }

    updateSessionActivity(sessionId, req) {
        if (!sessionId) return;
        
        this.authService.updateSessionActivity(sessionId, {
            lastActivity: new Date(),
            ipAddress: req.clientIP,
            userAgent: req.get('User-Agent'),
            path: req.path,
            method: req.method
        }).catch(error => {
            logger.error('Failed to update session activity', {
                sessionId,
                error: error.message
            });
        });
    }

    flagSuspiciousActivity(ip, type) {
        const key = `suspicious:${ip}`;
        const suspicious = this.suspiciousActivityStore.get(key);
        if (suspicious) {
            suspicious.score += 3;
            suspicious.events.push({
                timestamp: Date.now(),
                type,
                flagged: true
            });
        }
    }

    /**
     * Error response methods
     */
    sendAuthError(res, message, correlationId, statusCode = 401) {
        res.status(statusCode).json({
            success: false,
            error: message,
            correlationId,
            timestamp: new Date().toISOString()
        });
    }

    sendRateLimitError(res, correlationId) {
        res.status(429).json({
            success: false,
            error: 'Rate limit exceeded',
            correlationId,
            timestamp: new Date().toISOString(),
            retryAfter: Math.ceil(this.config.rateLimit.blockDuration / 1000)
        });
    }

    sendSuspiciousActivityError(res, correlationId) {
        res.status(403).json({
            success: false,
            error: 'Suspicious activity detected',
            correlationId,
            timestamp: new Date().toISOString()
        });
    }

    sendMFARequired(res, correlationId) {
        res.status(403).json({
            success: false,
            error: 'MFA verification required',
            correlationId,
            timestamp: new Date().toISOString(),
            mfaRequired: true
        });
    }

    /**
     * Enhanced cleanup expired sessions and failed attempts
     */
    cleanup() {
        const currentTime = Date.now();
        let cleanedSessions = 0;
        let cleanedAttempts = 0;
        let cleanedDevices = 0;
        let cleanedRateLimit = 0;
        let cleanedSuspicious = 0;

        // Clean expired sessions
        for (const [sessionId, session] of this.sessionStore.entries()) {
            if (currentTime - session.lastActive > this.sessionTimeout) {
                this.sessionStore.delete(sessionId);
                cleanedSessions++;
            }
        }

        // Clean old failed attempts
        for (const [identifier, attempts] of this.failedAttempts.entries()) {
            if (attempts.lockedUntil > 0 && attempts.lockedUntil < currentTime) {
                this.failedAttempts.delete(identifier);
                cleanedAttempts++;
            }
        }

        // Clean expired device trusts
        for (const [fingerprint, deviceInfo] of this.deviceFingerprints.entries()) {
            if (currentTime > deviceInfo.expiresAt) {
                this.deviceFingerprints.delete(fingerprint);
                cleanedDevices++;
            }
        }

        // Clean up rate limit store
        for (const [key, data] of this.rateLimitStore.entries()) {
            if (currentTime > data.resetTime && !data.blocked) {
                this.rateLimitStore.delete(key);
                cleanedRateLimit++;
            }
        }

        // Clean up suspicious activity store
        for (const [key, data] of this.suspiciousActivityStore.entries()) {
            if (currentTime > data.resetTime) {
                this.suspiciousActivityStore.delete(key);
                cleanedSuspicious++;
            }
        }

        if (cleanedSessions + cleanedAttempts + cleanedDevices + cleanedRateLimit + cleanedSuspicious > 0) {
            console.log(`🧹 Auth cleanup: ${cleanedSessions} sessions, ${cleanedAttempts} attempts, ${cleanedDevices} devices, ${cleanedRateLimit} rate limits, ${cleanedSuspicious} suspicious`);
        }
    }

    /**
     * Get authentication statistics
     */
    getStats() {
        return {
            activeSessions: this.sessionStore.size,
            failedAttempts: this.failedAttempts.size,
            trustedDevices: this.deviceFingerprints.size,
            lockedAccounts: Array.from(this.failedAttempts.values())
                .filter(attempt => attempt.lockedUntil > Date.now()).length
        };
    }

    /**
     * Revoke user sessions
     */
    revokeUserSessions(userId) {
        let revokedCount = 0;
        for (const [sessionId, session] of this.sessionStore.entries()) {
            if (session.userId === userId) {
                this.sessionStore.delete(sessionId);
                revokedCount++;
            }
        }
        console.log(`🔒 Revoked ${revokedCount} sessions for user ${userId}`);
        return revokedCount;
    }
}

// Factory functions for common middleware configurations
const createAuthMiddleware = (options = {}) => {
    const middleware = new EnhancedAuthMiddleware();
    return middleware.authenticate(options);
};

const requireAuth = createAuthMiddleware({ required: true });
const requireMFA = createAuthMiddleware({ required: true, requireMFA: true });
const requireRole = (roles) => createAuthMiddleware({ required: true, roles });
const requirePermissions = (permissions) => createAuthMiddleware({ required: true, permissions });

// Admin middleware
const requireAdmin = createAuthMiddleware({ 
    required: true, 
    roles: ['admin', 'super_admin'] 
});

// API middleware
const requireApiAccess = createAuthMiddleware({
    required: true,
    permissions: ['api_access']
});

// Trading middleware
const requireTradingAccess = createAuthMiddleware({
    required: true,
    requireMFA: true,
    permissions: ['trading_access']
});

// Legacy compatibility middleware
const createLegacyAuthMiddleware = (options = {}) => {
    const middleware = new EnhancedAuthMiddleware();
    return middleware.requireAuth(options);
};

module.exports = {
    EnhancedAuthMiddleware,
    createAuthMiddleware,
    createLegacyAuthMiddleware,
    requireAuth,
    requireMFA,
    requireRole,
    requirePermissions,
    requireAdmin,
    requireApiAccess,
    requireTradingAccess
};