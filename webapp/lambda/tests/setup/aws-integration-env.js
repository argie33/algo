/**
 * AWS Integration Test Environment Setup
 * Sets up real AWS environment variables for integration testing
 */

// Real AWS Configuration - No Mocks!
process.env.NODE_ENV = 'integration';
process.env.AWS_REGION = 'us-east-1';
process.env.DB_SECRET_ARN = 'arn:aws:secretsmanager:us-east-1:626216981288:secret:stocks-db-credentials-dev';
process.env.API_KEY_ENCRYPTION_SECRET_ARN = 'arn:aws:secretsmanager:us-east-1:626216981288:secret:api-key-encryption';

// Disable AWS SDK retries for faster test execution
process.env.AWS_MAX_ATTEMPTS = '3';
process.env.AWS_RETRY_MODE = 'standard';

// Test configuration
process.env.INTEGRATION_TEST = 'true';
process.env.REAL_AWS_TEST = 'true';

console.log('🚀 AWS Integration Test Environment Loaded');
console.log('📍 Region:', process.env.AWS_REGION);
console.log('🗄️ DB Secret:', process.env.DB_SECRET_ARN ? 'CONFIGURED' : 'MISSING');
console.log('🔐 API Secret:', process.env.API_KEY_ENCRYPTION_SECRET_ARN ? 'CONFIGURED' : 'MISSING');