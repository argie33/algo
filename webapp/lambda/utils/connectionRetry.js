/**
 * Database Connection Retry Logic
 * Implements exponential backoff and intelligent retry strategies
 */

class ConnectionRetry {
    constructor(options = {}) {
        this.maxRetries = options.maxRetries || 5;
        this.initialDelay = options.initialDelay || 1000; // 1 second
        this.maxDelay = options.maxDelay || 30000; // 30 seconds
        this.backoffMultiplier = options.backoffMultiplier || 2;
        this.jitterRange = options.jitterRange || 0.1; // 10% jitter
        this.retryableErrors = options.retryableErrors || [
            'ECONNREFUSED',
            'ENOTFOUND', 
            'ETIMEDOUT',
            'ECONNRESET',
            'EPIPE',
            'connection terminated unexpectedly',
            'Connection terminated',
            'server closed the connection unexpectedly',
            'timeout',
            'Circuit breaker'
        ];
    }

    /**
     * Check if an error is retryable
     */
    isRetryableError(error) {
        const errorMessage = error.message?.toLowerCase() || '';
        const errorCode = error.code?.toUpperCase() || '';
        
        return this.retryableErrors.some(retryableError => {
            const checkError = retryableError.toLowerCase();
            return errorMessage.includes(checkError) || errorCode === retryableError;
        });
    }

    /**
     * Calculate delay for next retry attempt
     */
    calculateDelay(attemptNumber) {
        // Exponential backoff: delay = initialDelay * (backoffMultiplier ^ attemptNumber)
        let delay = this.initialDelay * Math.pow(this.backoffMultiplier, attemptNumber);
        
        // Cap at max delay
        delay = Math.min(delay, this.maxDelay);
        
        // Add jitter to prevent thundering herd
        const jitter = delay * this.jitterRange * (Math.random() * 2 - 1);
        delay += jitter;
        
        return Math.max(delay, 0);
    }

    /**
     * Execute function with retry logic
     */
    async execute(fn, context = 'operation') {
        const retryId = Math.random().toString(36).substr(2, 9);
        let lastError;
        
        console.log(`🔄 [${retryId}] Starting ${context} with retry logic (max ${this.maxRetries} attempts)`);
        
        for (let attempt = 0; attempt <= this.maxRetries; attempt++) {
            try {
                const startTime = Date.now();
                const result = await fn(attempt);
                const duration = Date.now() - startTime;
                
                if (attempt > 0) {
                    console.log(`✅ [${retryId}] ${context} succeeded on attempt ${attempt + 1} after ${duration}ms`);
                } else {
                    console.log(`✅ [${retryId}] ${context} succeeded on first attempt in ${duration}ms`);
                }
                
                return {
                    success: true,
                    result,
                    attempts: attempt + 1,
                    totalDuration: duration,
                    retryId
                };
                
            } catch (error) {
                lastError = error;
                const isRetryable = this.isRetryableError(error);
                const isLastAttempt = attempt === this.maxRetries;
                
                console.error(`❌ [${retryId}] ${context} failed on attempt ${attempt + 1}:`, {
                    error: error.message,
                    code: error.code,
                    retryable: isRetryable,
                    lastAttempt: isLastAttempt
                });
                
                // Don't retry if error is not retryable or this is the last attempt
                if (!isRetryable || isLastAttempt) {
                    break;
                }
                
                // Calculate delay for next attempt
                const delay = this.calculateDelay(attempt);
                console.log(`⏳ [${retryId}] Retrying ${context} in ${delay}ms (attempt ${attempt + 2}/${this.maxRetries + 1})`);
                
                await this.delay(delay);
            }
        }
        
        console.error(`❌ [${retryId}] ${context} failed after ${this.maxRetries + 1} attempts`);
        
        return {
            success: false,
            error: lastError.message,
            code: lastError.code,
            attempts: this.maxRetries + 1,
            retryId,
            finalError: lastError
        };
    }

    /**
     * Utility delay function
     */
    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    /**
     * Create a retryable database connection function
     */
    createRetryableConnection(connectionFn) {
        return async () => {
            return this.execute(async (attempt) => {
                console.log(`🔌 Database connection attempt ${attempt + 1}`);
                return await connectionFn();
            }, 'database connection');
        };
    }

    /**
     * Create a retryable query function
     */
    createRetryableQuery(queryFn) {
        return async (text, params = []) => {
            return this.execute(async (attempt) => {
                console.log(`🔍 Database query attempt ${attempt + 1}: ${text.substring(0, 50)}...`);
                return await queryFn(text, params);
            }, 'database query');
        };
    }

    /**
     * Advanced retry with circuit breaker integration
     */
    async executeWithCircuitBreaker(fn, context = 'operation', circuitBreakerKey = null) {
        // If circuit breaker key is provided, check and manage circuit breaker
        if (circuitBreakerKey) {
            const timeoutHelper = require('./timeoutHelper');
            
            // Check if circuit breaker is open
            if (timeoutHelper.isCircuitOpen && timeoutHelper.isCircuitOpen(circuitBreakerKey)) {
                const error = new Error(`Circuit breaker open for ${circuitBreakerKey}`);
                error.code = 'CIRCUIT_BREAKER_OPEN';
                throw error;
            }
        }
        
        const result = await this.execute(fn, context);
        
        // Update circuit breaker based on result
        if (circuitBreakerKey) {
            const timeoutHelper = require('./timeoutHelper');
            
            if (result.success) {
                if (timeoutHelper.recordSuccess) {
                    timeoutHelper.recordSuccess(circuitBreakerKey);
                }
            } else {
                if (timeoutHelper.recordFailure) {
                    timeoutHelper.recordFailure(circuitBreakerKey);
                }
            }
        }
        
        return result;
    }

    /**
     * Get retry statistics for monitoring
     */
    getRetryStats(results) {
        if (!Array.isArray(results)) {
            results = [results];
        }
        
        const stats = {
            total: results.length,
            successful: 0,
            failed: 0,
            totalAttempts: 0,
            averageAttempts: 0,
            maxAttempts: 0,
            minAttempts: Infinity,
            retriedOperations: 0
        };
        
        results.forEach(result => {
            if (result.success) {
                stats.successful++;
            } else {
                stats.failed++;
            }
            
            stats.totalAttempts += result.attempts;
            stats.maxAttempts = Math.max(stats.maxAttempts, result.attempts);
            stats.minAttempts = Math.min(stats.minAttempts, result.attempts);
            
            if (result.attempts > 1) {
                stats.retriedOperations++;
            }
        });
        
        stats.averageAttempts = stats.totalAttempts / stats.total;
        stats.successRate = (stats.successful / stats.total) * 100;
        stats.retryRate = (stats.retriedOperations / stats.total) * 100;
        
        if (stats.minAttempts === Infinity) {
            stats.minAttempts = 0;
        }
        
        return stats;
    }
}

module.exports = ConnectionRetry;