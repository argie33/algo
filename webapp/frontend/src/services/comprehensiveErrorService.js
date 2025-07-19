/**
 * Comprehensive Error Service for Frontend
 * Handles all client-side errors with detailed logging and user feedback
 */

class ComprehensiveErrorService {
    constructor() {
        this.errorQueue = [];
        this.errorStats = {
            totalErrors: 0,
            criticalErrors: 0,
            networkErrors: 0,
            apiErrors: 0,
            componentErrors: 0
        };
        this.initializeGlobalErrorHandling();
    }

    /**
     * Initialize global error handling
     */
    initializeGlobalErrorHandling() {
        // Handle unhandled promise rejections
        window.addEventListener('unhandledrejection', (event) => {
            this.handleError(event.reason, {
                type: 'UNHANDLED_PROMISE_REJECTION',
                url: window.location.href,
                userAgent: navigator.userAgent
            });
        });

        // Handle global JavaScript errors
        window.addEventListener('error', (event) => {
            this.handleError(event.error, {
                type: 'GLOBAL_JAVASCRIPT_ERROR',
                filename: event.filename,
                lineno: event.lineno,
                colno: event.colno,
                url: window.location.href
            });
        });

        // Handle resource loading errors
        window.addEventListener('error', (event) => {
            if (event.target !== window) {
                this.handleError(new Error('Resource loading failed'), {
                    type: 'RESOURCE_LOADING_ERROR',
                    element: event.target.tagName,
                    source: event.target.src || event.target.href,
                    url: window.location.href
                });
            }
        }, true);
    }

    /**
     * Main error handling method
     */
    handleError(error, context = {}) {
        const errorInfo = this.analyzeError(error, context);
        
        // Log error details
        this.logError(errorInfo);
        
        // Update statistics
        this.updateErrorStats(errorInfo);
        
        // Queue for potential retry or user notification
        this.queueError(errorInfo);
        
        // Determine user notification strategy
        const notification = this.determineUserNotification(errorInfo);
        
        return {
            errorId: errorInfo.id,
            category: errorInfo.category,
            severity: errorInfo.severity,
            userMessage: notification.message,
            canRetry: notification.canRetry,
            suggestedActions: notification.actions
        };
    }

    /**
     * Analyze error and categorize
     */
    analyzeError(error, context) {
        const errorId = this.generateErrorId();
        const timestamp = new Date().toISOString();
        
        // Extract error information
        const errorInfo = {
            id: errorId,
            timestamp,
            message: error?.message || 'Unknown error',
            name: error?.name || 'Error',
            stack: error?.stack,
            context,
            url: window.location.href,
            userAgent: navigator.userAgent,
            viewport: {
                width: window.innerWidth,
                height: window.innerHeight
            }
        };

        // Categorize error
        errorInfo.category = this.categorizeError(error, context);
        errorInfo.severity = this.determineSeverity(error, errorInfo.category);
        errorInfo.diagnostics = this.getDiagnostics(error, errorInfo.category, context);

        return errorInfo;
    }

    /**
     * Categorize error type
     */
    categorizeError(error, context) {
        const message = error?.message?.toLowerCase() || '';
        const name = error?.name?.toLowerCase() || '';
        const contextType = context.type || '';

        // Network/API errors
        if (message.includes('fetch') || message.includes('network') || 
            message.includes('cors') || contextType.includes('API')) {
            return 'NETWORK_ERROR';
        }

        // React/Component errors
        if (name.includes('react') || message.includes('component') || 
            message.includes('hook') || contextType.includes('COMPONENT')) {
            return 'COMPONENT_ERROR';
        }

        // Authentication errors
        if (message.includes('unauthorized') || message.includes('forbidden') ||
            message.includes('token') || message.includes('auth')) {
            return 'AUTH_ERROR';
        }

        // Validation errors
        if (message.includes('validation') || message.includes('invalid') ||
            message.includes('required')) {
            return 'VALIDATION_ERROR';
        }

        // Resource loading errors
        if (contextType === 'RESOURCE_LOADING_ERROR') {
            return 'RESOURCE_ERROR';
        }

        // JavaScript/Runtime errors
        if (contextType === 'GLOBAL_JAVASCRIPT_ERROR' || name.includes('syntax') ||
            name.includes('reference') || name.includes('type')) {
            return 'RUNTIME_ERROR';
        }

        // Promise/Async errors
        if (contextType === 'UNHANDLED_PROMISE_REJECTION') {
            return 'ASYNC_ERROR';
        }

        return 'UNKNOWN_ERROR';
    }

    /**
     * Determine error severity
     */
    determineSeverity(error, category) {
        // Critical - app cannot function
        if (category === 'COMPONENT_ERROR' || category === 'RUNTIME_ERROR' ||
            error?.message?.includes('critical')) {
            return 'CRITICAL';
        }

        // High - major feature broken
        if (category === 'AUTH_ERROR' || category === 'NETWORK_ERROR') {
            return 'HIGH';
        }

        // Medium - feature degraded
        if (category === 'VALIDATION_ERROR' || category === 'RESOURCE_ERROR') {
            return 'MEDIUM';
        }

        // Low - minor issue
        return 'LOW';
    }

    /**
     * Get diagnostic information
     */
    getDiagnostics(error, category, context) {
        const diagnostics = {
            possibleCauses: [],
            suggestedFixes: [],
            troubleshooting: []
        };

        switch (category) {
            case 'NETWORK_ERROR':
                diagnostics.possibleCauses = [
                    'Internet connection lost',
                    'API server unavailable',
                    'CORS configuration issue',
                    'Request timeout'
                ];
                diagnostics.suggestedFixes = [
                    'Check internet connection',
                    'Refresh the page',
                    'Try again in a moment',
                    'Contact support if problem persists'
                ];
                break;

            case 'COMPONENT_ERROR':
                diagnostics.possibleCauses = [
                    'React component lifecycle issue',
                    'State management error',
                    'Props validation failure',
                    'Rendering error'
                ];
                diagnostics.suggestedFixes = [
                    'Refresh the page',
                    'Clear browser cache',
                    'Try using a different browser',
                    'Report the issue'
                ];
                break;

            case 'AUTH_ERROR':
                diagnostics.possibleCauses = [
                    'Session expired',
                    'Invalid credentials',
                    'Permission denied',
                    'Authentication service unavailable'
                ];
                diagnostics.suggestedFixes = [
                    'Log in again',
                    'Check your credentials',
                    'Contact administrator for permissions'
                ];
                break;

            case 'VALIDATION_ERROR':
                diagnostics.possibleCauses = [
                    'Invalid input format',
                    'Required field missing',
                    'Data constraint violation'
                ];
                diagnostics.suggestedFixes = [
                    'Check input format',
                    'Fill in all required fields',
                    'Verify data is correct'
                ];
                break;

            default:
                diagnostics.possibleCauses = ['Unknown error occurred'];
                diagnostics.suggestedFixes = ['Refresh page and try again'];
        }

        return diagnostics;
    }

    /**
     * Log error with comprehensive details
     */
    logError(errorInfo) {
        const logLevel = this.getLogLevel(errorInfo.severity);
        
        console.group(`🚨 ${errorInfo.category} - ${errorInfo.severity}`);
        console.log(`Error ID: ${errorInfo.id}`);
        console.log(`Message: ${errorInfo.message}`);
        console.log(`Timestamp: ${errorInfo.timestamp}`);
        console.log(`URL: ${errorInfo.url}`);
        
        if (errorInfo.stack) {
            console.log(`Stack Trace:`, errorInfo.stack);
        }
        
        if (errorInfo.context) {
            console.log(`Context:`, errorInfo.context);
        }
        
        console.log(`Diagnostics:`, errorInfo.diagnostics);
        console.groupEnd();

        // Send to external logging service if configured
        this.sendToExternalLogger(errorInfo);
    }

    /**
     * Update error statistics
     */
    updateErrorStats(errorInfo) {
        this.errorStats.totalErrors++;
        
        if (errorInfo.severity === 'CRITICAL') {
            this.errorStats.criticalErrors++;
        }
        
        switch (errorInfo.category) {
            case 'NETWORK_ERROR':
                this.errorStats.networkErrors++;
                break;
            case 'COMPONENT_ERROR':
                this.errorStats.componentErrors++;
                break;
            case 'API_ERROR':
                this.errorStats.apiErrors++;
                break;
        }
    }

    /**
     * Queue error for potential processing
     */
    queueError(errorInfo) {
        this.errorQueue.push(errorInfo);
        
        // Keep only last 100 errors
        if (this.errorQueue.length > 100) {
            this.errorQueue.shift();
        }
    }

    /**
     * Determine user notification strategy
     */
    determineUserNotification(errorInfo) {
        const baseNotification = {
            message: this.getUserFriendlyMessage(errorInfo),
            canRetry: false,
            actions: []
        };

        switch (errorInfo.category) {
            case 'NETWORK_ERROR':
                return {
                    ...baseNotification,
                    canRetry: true,
                    actions: ['retry', 'checkConnection', 'contactSupport']
                };

            case 'AUTH_ERROR':
                return {
                    ...baseNotification,
                    actions: ['login', 'contactSupport']
                };

            case 'VALIDATION_ERROR':
                return {
                    ...baseNotification,
                    canRetry: true,
                    actions: ['fixInput', 'retry']
                };

            case 'COMPONENT_ERROR':
                return {
                    ...baseNotification,
                    canRetry: true,
                    actions: ['refresh', 'retry', 'reportBug']
                };

            default:
                return {
                    ...baseNotification,
                    actions: ['refresh', 'contactSupport']
                };
        }
    }

    /**
     * Get user-friendly error message
     */
    getUserFriendlyMessage(errorInfo) {
        const messages = {
            'NETWORK_ERROR': 'Unable to connect to our servers. Please check your internet connection and try again.',
            'COMPONENT_ERROR': 'Something went wrong with the page display. Please refresh the page.',
            'AUTH_ERROR': 'Authentication issue. Please log in again.',
            'VALIDATION_ERROR': 'Please check your input and try again.',
            'RESOURCE_ERROR': 'Failed to load some resources. Please refresh the page.',
            'RUNTIME_ERROR': 'A technical error occurred. Please refresh the page.',
            'ASYNC_ERROR': 'An operation failed to complete. Please try again.',
            'UNKNOWN_ERROR': 'An unexpected error occurred. Please try again.'
        };

        return messages[errorInfo.category] || messages['UNKNOWN_ERROR'];
    }

    /**
     * Send error to external logging service
     */
    async sendToExternalLogger(errorInfo) {
        try {
            // Only send critical and high severity errors to external service
            if (errorInfo.severity === 'CRITICAL' || errorInfo.severity === 'HIGH') {
                await fetch('/api/client-errors', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(errorInfo)
                });
            }
        } catch (e) {
            // Silently fail if we can't log to external service
            console.warn('Failed to send error to external logger:', e);
        }
    }

    /**
     * Get error statistics
     */
    getErrorStats() {
        return {
            ...this.errorStats,
            recentErrors: this.errorQueue.slice(-10),
            queueLength: this.errorQueue.length,
            timestamp: new Date().toISOString()
        };
    }

    /**
     * Clear error queue
     */
    clearErrorQueue() {
        this.errorQueue = [];
    }

    /**
     * Generate unique error ID
     */
    generateErrorId() {
        const timestamp = Date.now();
        const random = Math.random().toString(36).substr(2, 9);
        return `CLI_${timestamp}_${random}`;
    }

    /**
     * Get appropriate log level
     */
    getLogLevel(severity) {
        const levels = {
            'CRITICAL': 'error',
            'HIGH': 'error',
            'MEDIUM': 'warn',
            'LOW': 'info'
        };
        return levels[severity] || 'log';
    }
}

// Create singleton instance
const comprehensiveErrorService = new ComprehensiveErrorService();

export default comprehensiveErrorService;