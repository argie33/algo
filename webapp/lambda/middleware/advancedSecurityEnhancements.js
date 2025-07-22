/**
 * Advanced Security Enhancements Middleware
 * Provides next-generation security features for financial trading platform
 * 
 * Features:
 * - Advanced threat detection with machine learning patterns
 * - Real-time behavioral analysis and anomaly detection
 * - Financial data specific security validations
 * - Advanced API security with smart rate limiting
 * - Geographic and time-based security controls
 * - Advanced cryptographic input validation
 */

const crypto = require('crypto');
const validator = require('validator');
const geoip = require('geoip-lite');
const logger = require('../utils/logger');

/**
 * Advanced threat patterns detection with ML-inspired scoring
 */
class ThreatDetectionEngine {
    constructor() {
        this.suspiciousPatterns = new Map();
        this.ipRiskScores = new Map();
        this.behaviorProfiles = new Map();
        this.trustedCountries = ['US', 'CA', 'GB', 'AU', 'DE', 'FR', 'NL', 'CH', 'SE', 'NO', 'DK'];
        this.cleanupInterval = setInterval(() => this.cleanup(), 3600000); // 1 hour cleanup
    }

    /**
     * Analyze request for suspicious patterns and assign risk score
     */
    analyzeRequest(req) {
        const analysis = {
            riskScore: 0,
            threats: [],
            behavioral: {},
            geographic: {},
            temporal: {},
            cryptographic: {}
        };

        // Geographic analysis
        const geo = geoip.lookup(req.ip);
        if (geo) {
            analysis.geographic = {
                country: geo.country,
                region: geo.region,
                city: geo.city,
                timezone: geo.timezone,
                isTrustedCountry: this.trustedCountries.includes(geo.country)
            };

            // Risk scoring based on geography
            if (!analysis.geographic.isTrustedCountry) {
                analysis.riskScore += 15;
                analysis.threats.push('UNTRUSTED_GEOGRAPHIC_LOCATION');
            }
        }

        // Temporal analysis
        const now = new Date();
        const hour = now.getHours();
        analysis.temporal = {
            hour,
            isBusinessHours: hour >= 6 && hour <= 22,
            timezone: geo?.timezone || 'unknown',
            isWeekend: [0, 6].includes(now.getDay())
        };

        // Risk scoring for off-hours access to financial data
        if (!analysis.temporal.isBusinessHours && this.isFinancialEndpoint(req.path)) {
            analysis.riskScore += 10;
            analysis.threats.push('OFF_HOURS_FINANCIAL_ACCESS');
        }

        // Behavioral analysis
        const clientId = this.getClientIdentifier(req);
        const behaviorProfile = this.getBehaviorProfile(clientId);
        
        analysis.behavioral = {
            requestFrequency: behaviorProfile.requestCount,
            averageRequestSize: behaviorProfile.avgSize,
            endpointDiversity: behaviorProfile.uniqueEndpoints.size,
            lastSeen: behaviorProfile.lastSeen,
            isNewClient: !behaviorProfile.established
        };

        // Update behavior profile
        this.updateBehaviorProfile(clientId, req);

        // Detect anomalous behavior
        if (behaviorProfile.requestCount > 1000 && !behaviorProfile.established) {
            analysis.riskScore += 20;
            analysis.threats.push('RAPID_REQUEST_PATTERN');
        }

        // Cryptographic analysis
        analysis.cryptographic = this.analyzeCryptographicPatterns(req);
        analysis.riskScore += analysis.cryptographic.riskScore;
        analysis.threats.push(...analysis.cryptographic.threats);

        // Advanced pattern analysis
        const patternAnalysis = this.analyzeAdvancedPatterns(req);
        analysis.riskScore += patternAnalysis.riskScore;
        analysis.threats.push(...patternAnalysis.threats);

        return analysis;
    }

    /**
     * Advanced cryptographic pattern analysis
     */
    analyzeCryptographicPatterns(req) {
        const analysis = { riskScore: 0, threats: [], patterns: [] };

        const checkCrypto = (value, path) => {
            if (typeof value !== 'string') return;

            // Detect encoded payloads
            const encodingPatterns = [
                { pattern: /^[A-Za-z0-9+/]+=*$/, type: 'BASE64', risk: 5 },
                { pattern: /^[A-Fa-f0-9]+$/, type: 'HEX', risk: 3 },
                { pattern: /%[0-9A-Fa-f]{2}/, type: 'URL_ENCODED', risk: 2 },
                { pattern: /\\x[0-9A-Fa-f]{2}/, type: 'HEX_ESCAPED', risk: 8 },
                { pattern: /\\u[0-9A-Fa-f]{4}/, type: 'UNICODE_ESCAPED', risk: 7 }
            ];

            encodingPatterns.forEach(({ pattern, type, risk }) => {
                if (pattern.test(value)) {
                    analysis.patterns.push({ type, path, sample: value.substring(0, 50) });
                    
                    // Higher risk for long encoded strings
                    if (value.length > 100) {
                        analysis.riskScore += risk * 2;
                        analysis.threats.push(`LONG_${type}_PAYLOAD`);
                    } else {
                        analysis.riskScore += risk;
                    }
                }
            });

            // Detect obfuscation attempts
            if (value.length > 200 && /[^\x20-\x7E]/.test(value)) {
                analysis.riskScore += 15;
                analysis.threats.push('OBFUSCATED_PAYLOAD');
            }
        };

        // Analyze all input sources
        this.traverseObject(req.body, 'body', checkCrypto);
        this.traverseObject(req.query, 'query', checkCrypto);
        this.traverseObject(req.headers, 'headers', checkCrypto);

        return analysis;
    }

    /**
     * Advanced pattern analysis using machine learning inspired techniques
     */
    analyzeAdvancedPatterns(req) {
        const analysis = { riskScore: 0, threats: [] };

        // Financial-specific attack patterns
        const financialThreats = [
            {
                name: 'ACCOUNT_ENUMERATION',
                patterns: [/account.*\d+/i, /user.*id.*\d+/i, /portfolio.*\d+/i],
                risk: 12
            },
            {
                name: 'FINANCIAL_DATA_EXTRACTION',
                patterns: [/balance/i, /transaction/i, /position/i, /trade/i],
                risk: 15,
                contextRequired: ['SELECT', 'UNION', 'OR', 'AND']
            },
            {
                name: 'TRADING_MANIPULATION',
                patterns: [/order.*cancel/i, /buy.*sell/i, /quantity.*0/i],
                risk: 25
            },
            {
                name: 'API_KEY_HARVESTING',
                patterns: [/api.*key/i, /secret/i, /token/i],
                risk: 20,
                contextRequired: ['SELECT', 'EXTRACT', 'DUMP']
            }
        ];

        const requestString = JSON.stringify({
            body: req.body,
            query: req.query,
            path: req.path
        });

        financialThreats.forEach(threat => {
            const matches = threat.patterns.filter(pattern => pattern.test(requestString));
            
            if (matches.length > 0) {
                let riskMultiplier = 1;
                
                // Check for contextual indicators
                if (threat.contextRequired) {
                    const contextMatches = threat.contextRequired.filter(context => 
                        new RegExp(context, 'i').test(requestString));
                    riskMultiplier = contextMatches.length > 0 ? 2 : 0.5;
                }
                
                analysis.riskScore += threat.risk * riskMultiplier;
                analysis.threats.push(threat.name);
            }
        });

        return analysis;
    }

    /**
     * Get or create behavior profile for client
     */
    getBehaviorProfile(clientId) {
        if (!this.behaviorProfiles.has(clientId)) {
            this.behaviorProfiles.set(clientId, {
                requestCount: 0,
                totalSize: 0,
                avgSize: 0,
                uniqueEndpoints: new Set(),
                firstSeen: new Date(),
                lastSeen: null,
                established: false,
                suspiciousActivity: [],
                riskHistory: []
            });
        }
        return this.behaviorProfiles.get(clientId);
    }

    /**
     * Update behavior profile with new request data
     */
    updateBehaviorProfile(clientId, req) {
        const profile = this.getBehaviorProfile(clientId);
        
        profile.requestCount++;
        profile.lastSeen = new Date();
        profile.uniqueEndpoints.add(req.path);
        
        const requestSize = JSON.stringify(req.body || {}).length + 
                           JSON.stringify(req.query || {}).length;
        profile.totalSize += requestSize;
        profile.avgSize = profile.totalSize / profile.requestCount;
        
        // Mark as established after 100 requests over 1+ hours
        if (profile.requestCount > 100 && 
            (profile.lastSeen - profile.firstSeen) > 3600000) {
            profile.established = true;
        }
    }

    /**
     * Generate client identifier for behavior tracking
     */
    getClientIdentifier(req) {
        const factors = [
            req.ip,
            req.get('User-Agent') || '',
            req.get('Accept-Language') || '',
            req.get('Accept-Encoding') || ''
        ];
        
        return crypto.createHash('sha256')
            .update(factors.join('|'))
            .digest('hex')
            .substring(0, 16);
    }

    /**
     * Check if endpoint handles financial data
     */
    isFinancialEndpoint(path) {
        const financialPaths = [
            '/api/portfolio', '/api/trading', '/api/orders', 
            '/api/positions', '/api/balance', '/api/transactions',
            '/api/settings', '/api/keys'
        ];
        
        return financialPaths.some(fp => path.includes(fp));
    }

    /**
     * Traverse object recursively for analysis
     */
    traverseObject(obj, path, callback) {
        if (!obj || typeof obj !== 'object') return;
        
        for (const [key, value] of Object.entries(obj)) {
            const currentPath = `${path}.${key}`;
            
            if (typeof value === 'string') {
                callback(value, currentPath);
            } else if (Array.isArray(value)) {
                value.forEach((item, index) => {
                    if (typeof item === 'string') {
                        callback(item, `${currentPath}[${index}]`);
                    } else if (typeof item === 'object') {
                        this.traverseObject(item, `${currentPath}[${index}]`, callback);
                    }
                });
            } else if (typeof value === 'object') {
                this.traverseObject(value, currentPath, callback);
            }
        }
    }

    /**
     * Cleanup old profiles and patterns
     */
    cleanup() {
        const now = new Date();
        const maxAge = 24 * 60 * 60 * 1000; // 24 hours
        
        // Clean behavior profiles
        for (const [clientId, profile] of this.behaviorProfiles.entries()) {
            if (now - profile.lastSeen > maxAge) {
                this.behaviorProfiles.delete(clientId);
            }
        }
        
        // Clean IP risk scores
        for (const [ip, data] of this.ipRiskScores.entries()) {
            if (now - data.lastUpdate > maxAge) {
                this.ipRiskScores.delete(ip);
            }
        }
    }
}

/**
 * Financial data specific validators with enhanced security
 */
class FinancialSecurityValidator {
    constructor() {
        this.suspiciousSymbols = [
            'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'DROP', 'UNION',
            'SCRIPT', 'ALERT', 'EVAL', 'FUNCTION', 'CONSTRUCTOR'
        ];
        this.maxFinancialValue = 1000000000; // 1 billion
        this.validCurrencies = new Set(['USD', 'EUR', 'GBP', 'JPY', 'CAD', 'AUD', 'CHF', 'SEK', 'NOK']);
    }

    /**
     * Validate financial symbol with advanced checks
     */
    validateFinancialSymbol(symbol) {
        if (!symbol || typeof symbol !== 'string') {
            throw new Error('Symbol must be a non-empty string');
        }

        const cleaned = symbol.trim().toUpperCase();
        
        // Length validation
        if (cleaned.length < 1 || cleaned.length > 12) {
            throw new Error('Symbol length must be between 1-12 characters');
        }

        // Character validation
        if (!/^[A-Z0-9.-]+$/.test(cleaned)) {
            throw new Error('Symbol contains invalid characters');
        }

        // Check against suspicious patterns
        if (this.suspiciousSymbols.some(sus => cleaned.includes(sus))) {
            logger.warn('Suspicious financial symbol pattern detected', {
                symbol: cleaned,
                original: symbol,
                pattern: 'INJECTION_ATTEMPT',
                suspiciousPatterns: this.suspiciousSymbols.filter(sus => cleaned.includes(sus))
            });
            throw new Error('Symbol contains suspicious patterns');
        }

        // Validate symbol structure patterns
        const validPatterns = [
            /^[A-Z]{1,5}$/,           // Basic stocks (AAPL, MSFT)
            /^[A-Z]{1,5}\.[A-Z]{1,2}$/,  // International (ASML.AS)
            /^[A-Z]{1,5}-[A-Z]$/,     // Preferred shares (BRK-A)
            /^[A-Z0-9]{1,12}$/        // Crypto or complex symbols
        ];

        if (!validPatterns.some(pattern => pattern.test(cleaned))) {
            throw new Error('Symbol does not match valid patterns');
        }

        return cleaned;
    }

    /**
     * Validate financial amount with comprehensive checks
     */
    validateFinancialAmount(amount, context = {}) {
        if (amount === null || amount === undefined) {
            throw new Error('Amount cannot be null or undefined');
        }

        let numericAmount;
        
        if (typeof amount === 'string') {
            // Remove currency symbols and formatting
            const cleaned = amount.replace(/[$,\s]/g, '');
            numericAmount = parseFloat(cleaned);
        } else {
            numericAmount = Number(amount);
        }

        if (isNaN(numericAmount)) {
            throw new Error('Amount must be a valid number');
        }

        if (!isFinite(numericAmount)) {
            throw new Error('Amount must be finite');
        }

        // Context-specific validation
        const { type = 'general', min = 0, max = this.maxFinancialValue } = context;

        if (numericAmount < min) {
            throw new Error(`Amount must be at least ${min}`);
        }

        if (numericAmount > max) {
            throw new Error(`Amount cannot exceed ${max}`);
        }

        // Type-specific validations
        switch (type) {
            case 'price':
                if (numericAmount <= 0) {
                    throw new Error('Price must be positive');
                }
                if (numericAmount > 1000000) { // $1M per share seems extreme
                    logger.warn('Unusually high financial price detected', {
                        price: numericAmount,
                        context: type,
                        threshold: 1000000
                    });
                }
                break;
                
            case 'quantity':
                if (!Number.isInteger(numericAmount)) {
                    throw new Error('Quantity must be an integer');
                }
                if (numericAmount <= 0) {
                    throw new Error('Quantity must be positive');
                }
                break;
                
            case 'percentage':
                if (numericAmount < 0 || numericAmount > 100) {
                    throw new Error('Percentage must be between 0-100');
                }
                break;
        }

        return numericAmount;
    }

    /**
     * Validate currency code
     */
    validateCurrency(currency) {
        if (!currency || typeof currency !== 'string') {
            throw new Error('Currency must be a non-empty string');
        }

        const cleaned = currency.trim().toUpperCase();
        
        if (cleaned.length !== 3) {
            throw new Error('Currency must be exactly 3 characters');
        }

        if (!this.validCurrencies.has(cleaned)) {
            throw new Error(`Unsupported currency: ${cleaned}`);
        }

        return cleaned;
    }

    /**
     * Validate trading order parameters
     */
    validateTradingOrder(order) {
        const errors = [];
        
        try {
            order.symbol = this.validateFinancialSymbol(order.symbol);
        } catch (e) {
            errors.push(`Symbol: ${e.message}`);
        }

        try {
            order.quantity = this.validateFinancialAmount(order.quantity, { type: 'quantity' });
        } catch (e) {
            errors.push(`Quantity: ${e.message}`);
        }

        if (order.price) {
            try {
                order.price = this.validateFinancialAmount(order.price, { type: 'price' });
            } catch (e) {
                errors.push(`Price: ${e.message}`);
            }
        }

        // Validate order type
        const validOrderTypes = ['market', 'limit', 'stop', 'stop_limit'];
        if (!validOrderTypes.includes(order.orderType)) {
            errors.push('Invalid order type');
        }

        // Validate side
        const validSides = ['buy', 'sell'];
        if (!validSides.includes(order.side)) {
            errors.push('Invalid order side');
        }

        if (errors.length > 0) {
            throw new Error(`Trading order validation failed: ${errors.join(', ')}`);
        }

        return order;
    }
}

// Initialize engines
const threatDetection = new ThreatDetectionEngine();
const financialValidator = new FinancialSecurityValidator();

/**
 * Advanced security middleware factory
 */
const createAdvancedSecurityMiddleware = (options = {}) => {
    const {
        enableThreatDetection = true,
        riskThreshold = 50,
        blockHighRisk = true,
        logAllRequests = false,
        enableFinancialValidation = true
    } = options;

    return async (req, res, next) => {
        try {
            let analysis = { riskScore: 0, threats: [] };

            // Threat detection analysis
            if (enableThreatDetection) {
                analysis = threatDetection.analyzeRequest(req);
                
                // Log high-risk requests
                if (analysis.riskScore > riskThreshold * 0.7 || logAllRequests) {
                    logger.warn('High-risk request detected', {
                        ip: req.ip,
                        path: req.path,
                        method: req.method,
                        riskScore: analysis.riskScore,
                        threats: analysis.threats,
                        geographic: analysis.geographic,
                        behavioral: analysis.behavioral,
                        userAgent: req.get('User-Agent')
                    });
                }

                // Block extremely high-risk requests
                if (blockHighRisk && analysis.riskScore > riskThreshold) {
                    return res.status(403).json({
                        success: false,
                        error: 'Security validation failed',
                        message: 'Request blocked due to high security risk',
                        code: 'HIGH_RISK_BLOCKED',
                        riskScore: analysis.riskScore,
                        threats: analysis.threats.slice(0, 3), // Limit exposed threat info
                        contactSupport: true
                    });
                }
            }

            // Financial validation for relevant endpoints
            if (enableFinancialValidation && financialValidator) {
                if (req.body && typeof req.body === 'object') {
                    // Auto-validate financial fields
                    if (req.body.symbol) {
                        req.body.symbol = financialValidator.validateFinancialSymbol(req.body.symbol);
                    }
                    if (req.body.currency) {
                        req.body.currency = financialValidator.validateCurrency(req.body.currency);
                    }
                    if (req.body.amount !== undefined) {
                        req.body.amount = financialValidator.validateFinancialAmount(req.body.amount);
                    }
                }
            }

            // Add security context to request
            req.securityAnalysis = analysis;
            
            next();
            
        } catch (error) {
            logger.error('Advanced security middleware error', {
                error,
                message: error.message,
                stack: error.stack,
                ip: req.ip,
                path: req.path,
                method: req.method,
                userAgent: req.get('User-Agent')
            });

            return res.status(400).json({
                success: false,
                error: 'Security validation failed',
                message: error.message,
                code: 'SECURITY_VALIDATION_ERROR'
            });
        }
    };
};

/**
 * Cleanup function for graceful shutdown
 */
const cleanup = () => {
    if (threatDetection.cleanupInterval) {
        clearInterval(threatDetection.cleanupInterval);
    }
};

process.on('SIGTERM', cleanup);
process.on('SIGINT', cleanup);

module.exports = {
    ThreatDetectionEngine,
    FinancialSecurityValidator,
    createAdvancedSecurityMiddleware,
    threatDetection,
    financialValidator,
    cleanup
};