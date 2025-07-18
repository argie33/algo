/**
 * Enhanced Input Validation and Sanitization Middleware
 * Provides comprehensive input validation and security protection for API endpoints
 * 
 * Features:
 * - Advanced XSS protection with HTML/JavaScript sanitization
 * - SQL injection prevention with pattern detection
 * - CSRF protection with token validation
 * - File upload security validation
 * - Advanced rate limiting with user-tier support
 * - NoSQL injection protection
 * - Command injection detection
 * - Data leakage prevention
 */

const rateLimit = require('express-rate-limit');
const slowDown = require('express-slow-down');
const helmet = require('helmet');
const validator = require('validator');
const crypto = require('crypto');
const path = require('path');

// Initialize DOMPurify for server-side HTML sanitization (fallback without JSDOM for Lambda)
let purify = null;
try {
    const DOMPurify = require('dompurify');
    const { JSDOM } = require('jsdom');
    const window = new JSDOM('').window;
    purify = DOMPurify(window);
} catch (error) {
    console.warn('DOMPurify not available, using basic HTML escaping');
    purify = {
        sanitize: (html) => validator.escape(html)
    };
}

/**
 * Enhanced security event logging
 */
function logSecurityEvent(type, details) {
    console.warn(`[SECURITY EVENT] ${type}:`, details);
    // In production, this would integrate with security monitoring systems
    // like AWS CloudWatch, Splunk, or dedicated SIEM solutions
}

/**
 * Advanced malicious pattern detection
 */
function containsMaliciousPatterns(input) {
    const patterns = [
        // XSS patterns
        /<script[^>]*>.*?<\/script>/gi,
        /javascript:/gi,
        /on\w+\s*=/gi,
        /vbscript:/gi,
        /data:text\/html/gi,
        
        // SQL injection patterns
        /(union\s+select|select\s+.*\s+from|insert\s+into|update\s+.*\s+set|delete\s+from)/gi,
        /(drop\s+table|alter\s+table|create\s+table)/gi,
        /(exec\s*\(|execute\s*\(|sp_|xp_)/gi,
        /('\s*(or|and)\s*'|'\s*(or|and)\s*\d)/gi,
        
        // NoSQL injection patterns
        /(\$where|\$regex|\$ne|\$gt|\$lt|\$gte|\$lte|\$in|\$nin)/gi,
        
        // Command injection patterns
        /(;\s*(cat|ls|pwd|whoami|id|uname)|\|\s*(cat|ls|pwd|whoami|id|uname))/gi,
        /(&&\s*(cat|ls|pwd|whoami|id|uname)|\|\|\s*(cat|ls|pwd|whoami|id|uname))/gi,
        
        // Path traversal patterns
        /(\.\.\/|\.\.\\|%2e%2e%2f|%2e%2e%5c)/gi,
        
        // Protocol smuggling
        /(file:\/\/|ftp:\/\/|gopher:\/\/|ldap:\/\/)/gi
    ];
    
    return patterns.some(pattern => pattern.test(input));
}

function detectMaliciousPatterns(input) {
    const detectedPatterns = [];
    const patterns = {
        'XSS': [/<script[^>]*>.*?<\/script>/gi, /javascript:/gi, /on\w+\s*=/gi],
        'SQL_INJECTION': [/(union\s+select|select\s+.*\s+from)/gi, /(drop\s+table|alter\s+table)/gi],
        'NOSQL_INJECTION': [/(\$where|\$regex|\$ne)/gi],
        'COMMAND_INJECTION': [/(;\s*(cat|ls|pwd)|\|\s*(cat|ls|pwd))/gi],
        'PATH_TRAVERSAL': [/(\.\.\/|\.\.\\)/gi]
    };
    
    Object.entries(patterns).forEach(([type, typePatterns]) => {
        if (typePatterns.some(pattern => pattern.test(input))) {
            detectedPatterns.push(type);
        }
    });
    
    return detectedPatterns;
}

/**
 * Enhanced input sanitization functions with comprehensive security checks
 */
const sanitizers = {
    // Enhanced string sanitization with XSS and injection protection
    string: (value, options = {}) => {
        if (typeof value !== 'string') return '';
        
        let sanitized = value.trim();
        
        // Remove null bytes and control characters
        sanitized = sanitized.replace(/[\0\x00-\x1f\x7f-\x9f]/g, '');
        
        // Detect and prevent various injection attempts
        if (containsMaliciousPatterns(sanitized)) {
            logSecurityEvent('MALICIOUS_INPUT_DETECTED', {
                input: sanitized.substring(0, 100),
                patterns: detectMaliciousPatterns(sanitized),
                timestamp: new Date().toISOString()
            });
            throw new Error('Potentially malicious input detected');
        }
        
        // Advanced HTML sanitization
        if (options.allowHTML) {
            sanitized = purify.sanitize(sanitized, {
                ALLOWED_TAGS: options.allowedTags || ['b', 'i', 'em', 'strong'],
                ALLOWED_ATTR: options.allowedAttributes || [],
                FORBID_SCRIPTS: true,
                FORBID_TAGS: ['script', 'object', 'embed', 'form', 'input'],
                STRIP_COMMENTS: true
            });
        } else if (options.escapeHTML) {
            sanitized = validator.escape(sanitized);
        }
        
        // Enhanced character filtering
        if (options.alphaNumOnly) {
            sanitized = sanitized.replace(/[^a-zA-Z0-9\s]/g, '');
        } else if (options.financialDataOnly) {
            // Allow financial symbols and decimal numbers
            sanitized = sanitized.replace(/[^a-zA-Z0-9\.\-\s]/g, '');
        }
        
        // Advanced length and content validation
        if (options.maxLength) {
            sanitized = sanitized.slice(0, options.maxLength);
        }
        
        // Normalize whitespace
        sanitized = sanitized.replace(/\s+/g, ' ').trim();
        
        return sanitized;
    },

    // Sanitize email input
    email: (value) => {
        if (!value || typeof value !== 'string') return '';
        return validator.normalizeEmail(value.trim()) || '';
    },

    // Sanitize numeric input
    number: (value, options = {}) => {
        const num = parseFloat(value);
        if (isNaN(num)) return options.defaultValue || 0;
        
        if (options.min !== undefined && num < options.min) return options.min;
        if (options.max !== undefined && num > options.max) return options.max;
        
        return num;
    },

    // Sanitize integer input
    integer: (value, options = {}) => {
        const num = parseInt(value);
        if (isNaN(num)) return options.defaultValue || 0;
        
        if (options.min !== undefined && num < options.min) return options.min;
        if (options.max !== undefined && num > options.max) return options.max;
        
        return num;
    },

    // Enhanced stock symbol sanitization with validation
    symbol: (value) => {
        if (!value || typeof value !== 'string') return '';
        let sanitized = value.trim().toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 10);
        
        // Validate against known stock symbol patterns
        if (sanitized.length < 1 || sanitized.length > 10) {
            throw new Error('Invalid stock symbol length');
        }
        
        // Check for suspicious patterns that might indicate injection attempts
        if (/^(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|SCRIPT)/i.test(sanitized)) {
            logSecurityEvent('SUSPICIOUS_SYMBOL_INPUT', {
                input: sanitized,
                timestamp: new Date().toISOString()
            });
            throw new Error('Invalid stock symbol format');
        }
        
        return sanitized;
    },
    
    // Enhanced file name sanitization
    fileName: (value) => {
        if (!value || typeof value !== 'string') return '';
        let sanitized = value.trim();
        
        // Remove path traversal attempts
        sanitized = sanitized.replace(/\.\.\//g, '').replace(/\.\.\\/g, '');
        
        // Remove dangerous characters
        sanitized = sanitized.replace(/[<>:"|?*\x00-\x1f]/g, '');
        
        // Limit to safe characters for file names
        sanitized = sanitized.replace(/[^a-zA-Z0-9._-]/g, '_');
        
        return sanitized.slice(0, 255); // Limit file name length
    },
    
    // Enhanced URL sanitization
    url: (value, options = {}) => {
        if (!value || typeof value !== 'string') return '';
        
        try {
            const url = new URL(value);
            
            // Check against allowed protocols
            const allowedProtocols = options.allowedProtocols || ['http:', 'https:'];
            if (!allowedProtocols.includes(url.protocol)) {
                throw new Error('Protocol not allowed');
            }
            
            // Check against blocked domains
            const blockedDomains = options.blockedDomains || [];
            if (blockedDomains.some(domain => url.hostname.includes(domain))) {
                throw new Error('Domain not allowed');
            }
            
            return url.toString();
        } catch (error) {
            logSecurityEvent('INVALID_URL_INPUT', {
                input: value.substring(0, 100),
                error: error.message,
                timestamp: new Date().toISOString()
            });
            throw new Error('Invalid URL format');
        }
    },

    // Sanitize boolean input
    boolean: (value) => {
        if (typeof value === 'boolean') return value;
        if (typeof value === 'string') {
            return ['true', '1', 'yes', 'on'].includes(value.toLowerCase());
        }
        return Boolean(value);
    }
};

/**
 * Enhanced rate limiting configurations with user-tier support
 */
const rateLimitConfigs = {
    // Strict rate limiting for authentication endpoints
    auth: rateLimit({
        windowMs: 15 * 60 * 1000, // 15 minutes
        max: 5, // 5 attempts per window
        message: {
            error: 'Too many authentication attempts, please try again later',
            retryAfter: 15 * 60, // 15 minutes in seconds
            securityEvent: 'EXCESSIVE_AUTH_ATTEMPTS'
        },
        standardHeaders: true,
        legacyHeaders: false,
        skip: (req) => {
            // Skip rate limiting in development mode
            return process.env.NODE_ENV === 'development';
        },
        handler: (req, res) => {
            // Log security event
            logSecurityEvent('EXCESSIVE_AUTH_ATTEMPTS', {
                ip: req.ip,
                userAgent: req.get('User-Agent'),
                timestamp: new Date().toISOString()
            });
            res.status(429).json({
                success: false,
                error: 'Too many authentication attempts',
                message: 'Your IP has been temporarily blocked due to excessive failed login attempts',
                retryAfter: 15 * 60,
                securityNotice: 'This incident has been logged for security monitoring'
            });
        }
    }),

    // Moderate rate limiting for API endpoints
    api: rateLimit({
        windowMs: 60 * 1000, // 1 minute
        max: 100, // 100 requests per minute
        message: {
            error: 'Too many API requests, please slow down',
            retryAfter: 60
        },
        standardHeaders: true,
        legacyHeaders: false,
        skip: (req) => {
            return process.env.NODE_ENV === 'development';
        }
    }),

    // Lenient rate limiting for trading endpoints (higher frequency needed)
    trading: rateLimit({
        windowMs: 60 * 1000, // 1 minute
        max: 200, // 200 requests per minute
        message: {
            error: 'Trading API rate limit exceeded',
            retryAfter: 60
        },
        standardHeaders: true,
        legacyHeaders: false,
        skip: (req) => {
            return process.env.NODE_ENV === 'development';
        }
    }),

    // Very strict rate limiting for resource-intensive endpoints
    heavy: rateLimit({
        windowMs: 5 * 60 * 1000, // 5 minutes
        max: 10, // 10 requests per 5 minutes
        message: {
            error: 'Rate limit exceeded for resource-intensive operation',
            retryAfter: 5 * 60
        },
        standardHeaders: true,
        legacyHeaders: false
    })
};

/**
 * Advanced injection prevention middleware with comprehensive protection
 */
const advancedInjectionPrevention = (req, res, next) => {
    const checkForInjection = (value, fieldPath = '') => {
        if (typeof value !== 'string') return { safe: true };
        
        // Enhanced injection patterns with specific detection
        const injectionChecks = {
            sql: {
                patterns: [
                    /(\s|^)(select|insert|update|delete|drop|create|alter|exec|execute|sp_|xp_)/i,
                    /(union\s+select|or\s+1\s*=\s*1|and\s+1\s*=\s*1)/i,
                    /('|";|--(\/\*|\*\/))/,
                    /(waitfor\s+delay|benchmark\s*\(|sleep\s*\()/i
                ],
                severity: 'HIGH'
            },
            nosql: {
                patterns: [
                    /(\$where|\$regex|\$ne|\$gt|\$lt|\$gte|\$lte|\$in|\$nin|\$or|\$and)/i,
                    /(this\.|constructor|prototype)/i
                ],
                severity: 'HIGH'
            },
            xss: {
                patterns: [
                    /<script[^>]*>.*?<\/script>/gi,
                    /(javascript:|vbscript:|data:text\/html)/i,
                    /(on\w+\s*=|style\s*=.*expression)/i,
                    /(<iframe|<object|<embed|<form)/i
                ],
                severity: 'HIGH'
            },
            command: {
                patterns: [
                    /(;\s*(cat|ls|pwd|whoami|id|uname|rm|mv|cp)|\|\s*(cat|ls|pwd|whoami|id|uname|rm|mv|cp))/i,
                    /(&&\s*(cat|ls|pwd|whoami|id|uname|rm|mv|cp)|\|\|\s*(cat|ls|pwd|whoami|id|uname|rm|mv|cp))/i,
                    /(`|\$\(|\$\{)/
                ],
                severity: 'CRITICAL'
            },
            ldap: {
                patterns: [
                    /(\*\)|\(\|\(|\)\(|\(\&\()/,
                    /(objectClass=|cn=|uid=|ou=)/i
                ],
                severity: 'MEDIUM'
            },
            xml: {
                patterns: [
                    /(<\?xml|<!\[CDATA\[|<!DOCTYPE)/i,
                    /(&lt;|&gt;|&quot;|&#)/
                ],
                severity: 'MEDIUM'
            }
        };
        
        for (const [type, check] of Object.entries(injectionChecks)) {
            const matches = check.patterns.filter(pattern => pattern.test(value));
            if (matches.length > 0) {
                return {
                    safe: false,
                    type,
                    severity: check.severity,
                    field: fieldPath,
                    matches: matches.length,
                    sample: value.substring(0, 100)
                };
            }
        }
        
        return { safe: true };
    };

    const checkObject = (obj, path = '') => {
        for (const [key, value] of Object.entries(obj)) {
            const currentPath = path ? `${path}.${key}` : key;
            
            if (typeof value === 'string') {
                const result = checkForInjection(value, currentPath);
                if (!result.safe) {
                    return result;
                }
            } else if (Array.isArray(value)) {
                for (let i = 0; i < value.length; i++) {
                    if (typeof value[i] === 'string') {
                        const result = checkForInjection(value[i], `${currentPath}[${i}]`);
                        if (!result.safe) {
                            return result;
                        }
                    } else if (typeof value[i] === 'object' && value[i] !== null) {
                        const nestedResult = checkObject(value[i], `${currentPath}[${i}]`);
                        if (nestedResult && !nestedResult.safe) {
                            return nestedResult;
                        }
                    }
                }
            } else if (typeof value === 'object' && value !== null) {
                const nestedResult = checkObject(value, currentPath);
                if (nestedResult && !nestedResult.safe) {
                    return nestedResult;
                }
            }
        }
        return null;
    };

    // Check all input sources
    const sources = [
        { data: req.query, name: 'query' },
        { data: req.body, name: 'body' },
        { data: req.params, name: 'params' },
        { data: req.headers, name: 'headers' }
    ].filter(source => source.data && typeof source.data === 'object');
    
    for (const source of sources) {
        const suspiciousInput = checkObject(source.data, source.name);
        if (suspiciousInput) {
            // Log detailed security event
            logSecurityEvent('INJECTION_ATTEMPT_DETECTED', {
                type: suspiciousInput.type,
                severity: suspiciousInput.severity,
                field: suspiciousInput.field,
                source: source.name,
                ip: req.ip,
                userAgent: req.get('User-Agent'),
                sample: suspiciousInput.sample,
                matches: suspiciousInput.matches,
                timestamp: new Date().toISOString()
            });
            
            // Block the request with detailed error for high severity
            if (suspiciousInput.severity === 'CRITICAL' || suspiciousInput.severity === 'HIGH') {
                return res.status(400).json({
                    success: false,
                    error: 'Security violation detected',
                    message: `Potentially malicious ${suspiciousInput.type.toUpperCase()} injection detected in ${suspiciousInput.field}`,
                    code: 'INJECTION_DETECTED',
                    severity: suspiciousInput.severity,
                    field: suspiciousInput.field,
                    securityNotice: 'This incident has been logged and monitored'
                });
            }
        }
    }

    next();
};

/**
 * CSRF protection middleware with enhanced token management
 */
const csrfProtection = (options = {}) => {
    const tokenStore = new Map(); // In production, use Redis or database
    const tokenExpiry = options.tokenExpiry || 3600000; // 1 hour
    
    return {
        generateToken: (req, res, next) => {
            const sessionId = req.sessionID || req.headers['x-session-id'] || 'anonymous';
            const token = crypto.randomBytes(32).toString('hex');
            const timestamp = Date.now();
            
            tokenStore.set(token, {
                sessionId,
                timestamp,
                used: false,
                ip: req.ip
            });
            
            // Clean expired tokens
            for (const [key, value] of tokenStore.entries()) {
                if (timestamp - value.timestamp > tokenExpiry) {
                    tokenStore.delete(key);
                }
            }
            
            req.csrfToken = token;
            res.set('X-CSRF-Token', token);
            next();
        },
        
        validateToken: (req, res, next) => {
            if (req.method === 'GET' || req.method === 'HEAD' || req.method === 'OPTIONS') {
                return next();
            }
            
            const token = req.headers['x-csrf-token'] || req.body._csrfToken;
            const sessionId = req.sessionID || req.headers['x-session-id'] || 'anonymous';
            
            if (!token) {
                logSecurityEvent('MISSING_CSRF_TOKEN', {
                    ip: req.ip,
                    method: req.method,
                    path: req.path,
                    timestamp: new Date().toISOString()
                });
                
                return res.status(403).json({
                    success: false,
                    error: 'CSRF token required',
                    message: 'Cross-site request forgery protection requires a valid token',
                    code: 'CSRF_TOKEN_MISSING'
                });
            }
            
            const tokenData = tokenStore.get(token);
            if (!tokenData || tokenData.used || tokenData.sessionId !== sessionId) {
                logSecurityEvent('INVALID_CSRF_TOKEN', {
                    ip: req.ip,
                    sessionId,
                    tokenProvided: !!token,
                    tokenExists: !!tokenData,
                    tokenUsed: tokenData?.used,
                    sessionMatch: tokenData?.sessionId === sessionId,
                    timestamp: new Date().toISOString()
                });
                
                return res.status(403).json({
                    success: false,
                    error: 'Invalid CSRF token',
                    message: 'The provided CSRF token is invalid or has been used',
                    code: 'CSRF_TOKEN_INVALID'
                });
            }
            
            // Check token expiry
            if (Date.now() - tokenData.timestamp > tokenExpiry) {
                tokenStore.delete(token);
                
                return res.status(403).json({
                    success: false,
                    error: 'CSRF token expired',
                    message: 'The CSRF token has expired, please refresh and try again',
                    code: 'CSRF_TOKEN_EXPIRED'
                });
            }
            
            // Mark token as used (one-time use)
            tokenData.used = true;
            next();
        }
    };
};

/**
 * File upload security validation
 */
const fileUploadSecurity = (options = {}) => {
    const allowedMimeTypes = options.allowedMimeTypes || [
        'image/jpeg', 'image/png', 'image/gif', 'image/webp',
        'application/pdf', 'text/csv', 'application/json'
    ];
    const maxFileSize = options.maxFileSize || 10 * 1024 * 1024; // 10MB
    const allowedExtensions = options.allowedExtensions || ['.jpg', '.jpeg', '.png', '.gif', '.pdf', '.csv', '.json'];
    
    return (req, res, next) => {
        if (!req.files || Object.keys(req.files).length === 0) {
            return next();
        }
        
        for (const [fieldName, file] of Object.entries(req.files)) {
            // Check file size
            if (file.size > maxFileSize) {
                logSecurityEvent('OVERSIZED_FILE_UPLOAD', {
                    fileName: file.name,
                    size: file.size,
                    maxSize: maxFileSize,
                    ip: req.ip,
                    timestamp: new Date().toISOString()
                });
                
                return res.status(413).json({
                    success: false,
                    error: 'File too large',
                    message: `File ${file.name} exceeds maximum size of ${maxFileSize} bytes`,
                    field: fieldName
                });
            }
            
            // Check MIME type
            if (!allowedMimeTypes.includes(file.mimetype)) {
                logSecurityEvent('INVALID_FILE_TYPE', {
                    fileName: file.name,
                    mimeType: file.mimetype,
                    allowedTypes: allowedMimeTypes,
                    ip: req.ip,
                    timestamp: new Date().toISOString()
                });
                
                return res.status(400).json({
                    success: false,
                    error: 'Invalid file type',
                    message: `File type ${file.mimetype} not allowed`,
                    allowedTypes: allowedMimeTypes,
                    field: fieldName
                });
            }
            
            // Check file extension
            const fileExtension = path.extname(file.name).toLowerCase();
            if (!allowedExtensions.includes(fileExtension)) {
                logSecurityEvent('INVALID_FILE_EXTENSION', {
                    fileName: file.name,
                    extension: fileExtension,
                    allowedExtensions,
                    ip: req.ip,
                    timestamp: new Date().toISOString()
                });
                
                return res.status(400).json({
                    success: false,
                    error: 'Invalid file extension',
                    message: `File extension ${fileExtension} not allowed`,
                    allowedExtensions,
                    field: fieldName
                });
            }
            
            // Sanitize filename
            file.safeName = sanitizers.fileName(file.name);
        }
        
        next();
    };
};

/**
 * Enhanced request size limiting with security monitoring
 */
const requestSizeLimit = (limit = '1mb', options = {}) => {
    return (req, res, next) => {
        const contentLength = req.get('content-length');
        const maxRequests = options.maxRequestsPerMinute || 60;
        
        // Track request sizes per IP for anomaly detection
        const clientIP = req.ip || req.connection.remoteAddress;
        
        if (contentLength) {
            const sizeInBytes = parseInt(contentLength);
            const limitInBytes = limit.includes('mb') ? 
                parseInt(limit) * 1024 * 1024 : 
                parseInt(limit);
            
            if (sizeInBytes > limitInBytes) {
                logSecurityEvent('OVERSIZED_REQUEST', {
                    ip: clientIP,
                    size: sizeInBytes,
                    limit: limitInBytes,
                    userAgent: req.get('User-Agent'),
                    timestamp: new Date().toISOString()
                });
                
                return res.status(413).json({
                    success: false,
                    error: 'Request too large',
                    message: `Request size ${sizeInBytes} bytes exceeds limit of ${limitInBytes} bytes`,
                    maxSize: limit,
                    code: 'PAYLOAD_TOO_LARGE'
                });
            }
            
            // Monitor for suspiciously large requests from same IP
            if (sizeInBytes > limitInBytes * 0.8) { // 80% of limit
                logSecurityEvent('LARGE_REQUEST_WARNING', {
                    ip: clientIP,
                    size: sizeInBytes,
                    percentage: (sizeInBytes / limitInBytes) * 100,
                    timestamp: new Date().toISOString()
                });
            }
        }
        
        next();
    };
};

module.exports = {
    rateLimitConfigs,
    sanitizers,
    requestSizeLimit,
    advancedInjectionPrevention,
    csrfProtection,
    fileUploadSecurity,
    logSecurityEvent,
    containsMaliciousPatterns,
    detectMaliciousPatterns
};