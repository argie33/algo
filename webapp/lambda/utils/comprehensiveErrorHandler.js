/**
 * Comprehensive Error Handler for Financial Dashboard
 * Catches all errors, provides detailed diagnostics, and implements recovery strategies
 */

const winston = require('winston');

class ComprehensiveErrorHandler {
    constructor() {
        this.initializeLogger();
        this.errorCounts = new Map();
        this.criticalErrors = [];
        this.startTime = Date.now();
    }

    initializeLogger() {
        this.logger = winston.createLogger({
            level: 'debug',
            format: winston.format.combine(
                winston.format.timestamp(),
                winston.format.errors({ stack: true }),
                winston.format.json()
            ),
            transports: [
                new winston.transports.Console({
                    format: winston.format.combine(
                        winston.format.colorize(),
                        winston.format.simple()
                    )
                })
            ]
        });
    }

    /**
     * Main error handling method - catches and categorizes all errors
     */
    handleError(error, context = {}) {
        const errorInfo = this.analyzeError(error, context);
        
        // Log comprehensive error details
        this.logErrorDetails(errorInfo);
        
        // Track error frequency
        this.trackErrorFrequency(errorInfo);
        
        // Determine response strategy
        const response = this.determineErrorResponse(errorInfo);
        
        // Log recovery action
        this.logger.info(`🔧 Recovery Action: ${response.action}`, {
            errorId: errorInfo.id,
            action: response.action,
            canRecover: response.canRecover
        });

        return response;
    }

    /**
     * Analyze error and extract comprehensive information
     */
    analyzeError(error, context) {
        const errorId = this.generateErrorId();
        const timestamp = new Date().toISOString();
        
        // Extract error details
        const errorDetails = {
            id: errorId,
            timestamp,
            name: error.name,
            message: error.message,
            stack: error.stack,
            code: error.code,
            errno: error.errno,
            syscall: error.syscall,
            context: context
        };

        // Categorize error type
        const category = this.categorizeError(error);
        
        // Determine severity
        const severity = this.determineSeverity(error, category);
        
        // Get diagnostic information
        const diagnostics = this.getDiagnostics(error, category, context);
        
        return {
            ...errorDetails,
            category,
            severity,
            diagnostics
        };
    }

    /**
     * Categorize error by type for targeted handling
     */
    categorizeError(error) {
        const message = error.message?.toLowerCase() || '';
        const name = error.name?.toLowerCase() || '';
        const code = error.code;

        // Database errors
        if (name.includes('sequelize') || message.includes('database') || 
            message.includes('connection') || code === 'ECONNREFUSED') {
            return 'DATABASE_ERROR';
        }

        // Authentication errors
        if (message.includes('unauthorized') || message.includes('forbidden') ||
            message.includes('token') || message.includes('auth')) {
            return 'AUTH_ERROR';
        }

        // Network errors
        if (code === 'ENOTFOUND' || code === 'ETIMEDOUT' || code === 'ECONNRESET' ||
            message.includes('network') || message.includes('fetch')) {
            return 'NETWORK_ERROR';
        }

        // API errors
        if (message.includes('api') || message.includes('endpoint') ||
            message.includes('400') || message.includes('500')) {
            return 'API_ERROR';
        }

        // Validation errors
        if (message.includes('validation') || message.includes('invalid') ||
            message.includes('required') || name.includes('validation')) {
            return 'VALIDATION_ERROR';
        }

        // File system errors
        if (code === 'ENOENT' || code === 'EACCES' || message.includes('file')) {
            return 'FILESYSTEM_ERROR';
        }

        // Memory/Performance errors
        if (message.includes('memory') || message.includes('heap') ||
            message.includes('timeout') && !message.includes('network')) {
            return 'PERFORMANCE_ERROR';
        }

        // Configuration errors
        if (message.includes('config') || message.includes('environment') ||
            message.includes('variable')) {
            return 'CONFIG_ERROR';
        }

        return 'UNKNOWN_ERROR';
    }

    /**
     * Determine error severity for escalation
     */
    determineSeverity(error, category) {
        // Critical - system cannot function
        if (category === 'DATABASE_ERROR' || category === 'CONFIG_ERROR' ||
            error.message?.includes('critical') || error.name === 'Error' && 
            error.message?.includes('Cannot read property')) {
            return 'CRITICAL';
        }

        // High - major feature broken
        if (category === 'AUTH_ERROR' || category === 'API_ERROR' ||
            category === 'NETWORK_ERROR') {
            return 'HIGH';
        }

        // Medium - feature degraded
        if (category === 'VALIDATION_ERROR' || category === 'PERFORMANCE_ERROR') {
            return 'MEDIUM';
        }

        // Low - minor issue
        return 'LOW';
    }

    /**
     * Get detailed diagnostics for troubleshooting
     */
    getDiagnostics(error, category, context) {
        const diagnostics = {
            possibleCauses: [],
            suggestedFixes: [],
            healthChecks: [],
            relatedSystems: []
        };

        switch (category) {
            case 'DATABASE_ERROR':
                diagnostics.possibleCauses = [
                    'Database connection pool exhausted',
                    'Database server unavailable',
                    'Network connectivity issues',
                    'Authentication failure',
                    'Database query timeout',
                    'SSL configuration issues'
                ];
                diagnostics.suggestedFixes = [
                    'Check database server status',
                    'Verify connection string',
                    'Review SSL certificate configuration',
                    'Check network security groups',
                    'Restart connection pool'
                ];
                diagnostics.healthChecks = [
                    'Database ping test',
                    'Connection pool status',
                    'SSL handshake test'
                ];
                diagnostics.relatedSystems = ['RDS', 'VPC', 'Security Groups'];
                break;

            case 'AUTH_ERROR':
                diagnostics.possibleCauses = [
                    'Invalid JWT token',
                    'Token expired',
                    'User session invalid',
                    'Permission denied',
                    'API key invalid'
                ];
                diagnostics.suggestedFixes = [
                    'Refresh user token',
                    'Check user permissions',
                    'Verify API key configuration',
                    'Review authentication flow'
                ];
                diagnostics.relatedSystems = ['Cognito', 'JWT', 'API Gateway'];
                break;

            case 'NETWORK_ERROR':
                diagnostics.possibleCauses = [
                    'Internet connectivity lost',
                    'DNS resolution failure',
                    'Firewall blocking request',
                    'Service unavailable',
                    'Request timeout'
                ];
                diagnostics.suggestedFixes = [
                    'Check internet connection',
                    'Verify DNS settings',
                    'Review firewall rules',
                    'Implement retry logic'
                ];
                diagnostics.relatedSystems = ['API Gateway', 'External APIs', 'CDN'];
                break;

            case 'API_ERROR':
                diagnostics.possibleCauses = [
                    'API endpoint unavailable',
                    'Invalid request format',
                    'Rate limiting',
                    'Server overload',
                    'API version mismatch'
                ];
                diagnostics.suggestedFixes = [
                    'Check API status',
                    'Validate request format',
                    'Implement rate limiting',
                    'Add circuit breaker'
                ];
                diagnostics.relatedSystems = ['Lambda', 'API Gateway', 'External APIs'];
                break;

            default:
                diagnostics.possibleCauses = ['Unknown error occurred'];
                diagnostics.suggestedFixes = ['Review error details and context'];
        }

        return diagnostics;
    }

    /**
     * Log comprehensive error details
     */
    logErrorDetails(errorInfo) {
        this.logger.error('🚨 COMPREHENSIVE ERROR REPORT', {
            errorId: errorInfo.id,
            category: errorInfo.category,
            severity: errorInfo.severity,
            name: errorInfo.name,
            message: errorInfo.message,
            context: errorInfo.context,
            diagnostics: errorInfo.diagnostics,
            stack: errorInfo.stack
        });

        // Log user-friendly error summary
        this.logger.error(`❌ [${errorInfo.category}] ${errorInfo.message}`, {
            errorId: errorInfo.id,
            severity: errorInfo.severity,
            timestamp: errorInfo.timestamp
        });

        // Log diagnostic information
        this.logger.info('🔍 DIAGNOSTIC INFORMATION', {
            errorId: errorInfo.id,
            possibleCauses: errorInfo.diagnostics.possibleCauses,
            suggestedFixes: errorInfo.diagnostics.suggestedFixes,
            relatedSystems: errorInfo.diagnostics.relatedSystems
        });
    }

    /**
     * Track error frequency for pattern detection
     */
    trackErrorFrequency(errorInfo) {
        const key = `${errorInfo.category}:${errorInfo.name}`;
        const count = this.errorCounts.get(key) || 0;
        this.errorCounts.set(key, count + 1);

        // Alert on high frequency errors
        if (count + 1 >= 5) {
            this.logger.warn(`⚠️ HIGH FREQUENCY ERROR DETECTED`, {
                errorType: key,
                count: count + 1,
                timeWindow: '1 hour'
            });
        }

        // Track critical errors
        if (errorInfo.severity === 'CRITICAL') {
            this.criticalErrors.push(errorInfo);
            this.logger.error(`🔥 CRITICAL ERROR LOGGED`, {
                errorId: errorInfo.id,
                totalCritical: this.criticalErrors.length
            });
        }
    }

    /**
     * Determine appropriate error response
     */
    determineErrorResponse(errorInfo) {
        const baseResponse = {
            success: false,
            errorId: errorInfo.id,
            category: errorInfo.category,
            severity: errorInfo.severity,
            message: this.getUserFriendlyMessage(errorInfo),
            canRecover: false,
            action: 'LOG_AND_FAIL'
        };

        switch (errorInfo.category) {
            case 'DATABASE_ERROR':
                return {
                    ...baseResponse,
                    canRecover: true,
                    action: 'RETRY_WITH_BACKOFF',
                    retryAfter: 5000,
                    maxRetries: 3
                };

            case 'NETWORK_ERROR':
                return {
                    ...baseResponse,
                    canRecover: true,
                    action: 'RETRY_WITH_EXPONENTIAL_BACKOFF',
                    retryAfter: 2000,
                    maxRetries: 5
                };

            case 'AUTH_ERROR':
                return {
                    ...baseResponse,
                    action: 'REDIRECT_TO_LOGIN',
                    redirectUrl: '/login'
                };

            case 'VALIDATION_ERROR':
                return {
                    ...baseResponse,
                    canRecover: true,
                    action: 'RETURN_VALIDATION_ERROR',
                    validationErrors: this.extractValidationErrors(errorInfo)
                };

            default:
                return {
                    ...baseResponse,
                    action: 'RETURN_GENERIC_ERROR'
                };
        }
    }

    /**
     * Generate user-friendly error message
     */
    getUserFriendlyMessage(errorInfo) {
        const messages = {
            'DATABASE_ERROR': 'Unable to connect to database. Please try again in a moment.',
            'AUTH_ERROR': 'Authentication failed. Please log in again.',
            'NETWORK_ERROR': 'Network connection issue. Please check your internet connection.',
            'API_ERROR': 'Service temporarily unavailable. Please try again later.',
            'VALIDATION_ERROR': 'Please check your input and try again.',
            'PERFORMANCE_ERROR': 'The system is running slowly. Please wait a moment.',
            'CONFIG_ERROR': 'System configuration error. Please contact support.',
            'UNKNOWN_ERROR': 'An unexpected error occurred. Please try again.'
        };

        return messages[errorInfo.category] || messages['UNKNOWN_ERROR'];
    }

    /**
     * Extract validation errors for user feedback
     */
    extractValidationErrors(errorInfo) {
        const errors = [];
        const message = errorInfo.message;
        
        // Common validation patterns
        if (message.includes('required')) {
            errors.push('Required field is missing');
        }
        if (message.includes('invalid')) {
            errors.push('Invalid input format');
        }
        if (message.includes('length')) {
            errors.push('Input length is invalid');
        }

        return errors.length > 0 ? errors : ['Validation failed'];
    }

    /**
     * Generate unique error ID for tracking
     */
    generateErrorId() {
        const timestamp = Date.now();
        const random = Math.random().toString(36).substr(2, 9);
        return `ERR_${timestamp}_${random}`;
    }

    /**
     * Get error statistics for monitoring
     */
    getErrorStats() {
        const uptime = Date.now() - this.startTime;
        const totalErrors = Array.from(this.errorCounts.values()).reduce((a, b) => a + b, 0);
        
        return {
            uptime: uptime,
            totalErrors: totalErrors,
            criticalErrors: this.criticalErrors.length,
            errorTypes: Object.fromEntries(this.errorCounts),
            errorRate: totalErrors / (uptime / 1000 / 60) // errors per minute
        };
    }

    /**
     * Express middleware wrapper
     */
    expressMiddleware() {
        return (error, req, res, next) => {
            const context = {
                method: req.method,
                url: req.url,
                userAgent: req.headers['user-agent'],
                ip: req.ip,
                body: req.body,
                params: req.params,
                query: req.query
            };

            const errorResponse = this.handleError(error, context);
            
            // Determine HTTP status code
            let statusCode = 500;
            if (errorResponse.category === 'AUTH_ERROR') statusCode = 401;
            if (errorResponse.category === 'VALIDATION_ERROR') statusCode = 400;
            if (errorResponse.category === 'NETWORK_ERROR') statusCode = 503;

            res.status(statusCode).json({
                success: false,
                error: {
                    id: errorResponse.errorId,
                    message: errorResponse.message,
                    category: errorResponse.category,
                    severity: errorResponse.severity,
                    canRetry: errorResponse.canRecover,
                    timestamp: new Date().toISOString()
                }
            });
        };
    }
}

module.exports = new ComprehensiveErrorHandler();