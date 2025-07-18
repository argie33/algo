/**
 * Enhanced Authentication and Authorization Middleware
 * Advanced security features for financial trading platform
 */

const jwt = require('jsonwebtoken');
const crypto = require('crypto');

class EnhancedAuthMiddleware {
    constructor() {
        this.jwtSecret = process.env.JWT_SECRET || 'fallback-secret-change-in-production';
        this.sessionStore = new Map(); // In production, use Redis
        this.failedAttempts = new Map();
        this.deviceFingerprints = new Map();
        
        // Security settings
        this.maxFailedAttempts = 5;
        this.lockoutDuration = 30 * 60 * 1000; // 30 minutes
        this.sessionTimeout = 24 * 60 * 60 * 1000; // 24 hours
        this.deviceTrustDuration = 7 * 24 * 60 * 60 * 1000; // 7 days
        
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
     * Main authentication middleware
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
     * Cleanup expired sessions and failed attempts
     */
    cleanup() {
        const currentTime = Date.now();
        let cleanedSessions = 0;
        let cleanedAttempts = 0;
        let cleanedDevices = 0;

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

        if (cleanedSessions + cleanedAttempts + cleanedDevices > 0) {
            console.log(`🧹 Auth cleanup: ${cleanedSessions} sessions, ${cleanedAttempts} attempts, ${cleanedDevices} devices`);
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

module.exports = EnhancedAuthMiddleware;