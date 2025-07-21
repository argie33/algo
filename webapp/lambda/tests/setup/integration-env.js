/**
 * Integration Test Environment Setup
 * Sets up environment variables for integration tests with AWS services
 */

// Set test environment
process.env.NODE_ENV = 'test';

// AWS Configuration
process.env.AWS_REGION = process.env.AWS_REGION || 'us-east-1';

// Integration test specific environment variables
process.env.USE_REAL_AWS = 'true';
process.env.INTEGRATION_TEST = 'true';

// Database configuration for integration tests
// Use DB_SECRET_ARN from GitHub Actions environment
if (process.env.DB_SECRET_ARN) {
  console.log('Using DB_SECRET_ARN from environment:', process.env.DB_SECRET_ARN);
} else {
  console.log('DB_SECRET_ARN not found in environment, will use fallback configuration');
}

process.env.DB_SSL = 'false'; // Test environment doesn't need SSL
process.env.DB_POOL_MAX = '5'; // Smaller pool for tests
process.env.DB_POOL_IDLE_TIMEOUT = '30000';
process.env.DB_CONNECT_TIMEOUT = '10000';

// Authentication configuration for integration tests
process.env.ALLOW_DEV_AUTH_BYPASS = 'true'; // Allow auth bypass for integration tests
process.env.COGNITO_USER_POOL_ID = process.env.TEST_USER_POOL_ID || 'test-pool-id';
process.env.COGNITO_CLIENT_ID = process.env.TEST_USER_POOL_CLIENT_ID || 'test-client-id';

// Timeouts
process.env.REQUEST_TIMEOUT = '30000';
process.env.DATABASE_TIMEOUT = '15000';

// Logging configuration for tests
process.env.LOG_LEVEL = 'error'; // Reduce noise in test output
process.env.DISABLE_CONSOLE_LOGS = 'false'; // Keep important logs for debugging

// Performance monitoring (disabled for tests to prevent memory leaks)
process.env.PERFORMANCE_MONITORING_ENABLED = 'false';
process.env.DISABLE_PERFORMANCE_MONITORING = 'true';

// Circuit breaker configuration for tests
process.env.CIRCUIT_BREAKER_ENABLED = 'true';
process.env.CIRCUIT_BREAKER_FAILURE_THRESHOLD = '3';
process.env.CIRCUIT_BREAKER_RESET_TIMEOUT = '10000';

// Rate limiting (disabled for tests)
process.env.RATE_LIMIT_ENABLED = 'false';

// Cache configuration (disabled for tests)
process.env.CACHE_ENABLED = 'false';

console.log('🔧 Integration test environment variables configured');