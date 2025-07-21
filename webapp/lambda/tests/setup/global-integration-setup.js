/**
 * Global Integration Test Setup
 * Runs once before all integration tests
 */

// Use AWS SDK v3 (as per package.json dependencies)
let STSClient;
try {
  const { STSClient: STS } = require('@aws-sdk/client-sts');
  const { GetCallerIdentityCommand } = require('@aws-sdk/client-sts');
  STSClient = STS;
  global.GetCallerIdentityCommand = GetCallerIdentityCommand;
} catch (error) {
  console.warn('⚠️ AWS SDK v3 not available - integration tests may be skipped');
  STSClient = null;
}

module.exports = async () => {
  console.log('🚀 Starting global integration test setup...');
  
  try {
    // Verify AWS credentials are available
    if (STSClient) {
      const sts = new STSClient({ region: process.env.AWS_REGION || 'us-east-1' });
      const identity = await sts.send(new global.GetCallerIdentityCommand({}));
      console.log('✅ AWS credentials verified:', identity.Account);
    } else {
      console.log('⚠️ AWS SDK not available - skipping credential verification');
    }
    
    // Verify required environment variables
    const requiredEnvVars = [
      'TEST_DB_SECRET_ARN',
      'TEST_STACK_NAME',
      'AWS_REGION'
    ];
    
    const missingVars = requiredEnvVars.filter(varName => !process.env[varName]);
    
    if (missingVars.length > 0) {
      console.warn('⚠️ Missing environment variables:', missingVars.join(', '));
      console.log('Integration tests may be skipped if infrastructure is not available');
    } else {
      console.log('✅ All required environment variables are set');
    }
    
    // Note: jest.setTimeout should be called in setupFilesAfterEnv, not globalSetup
    
    console.log('✅ Global integration test setup completed');
    
  } catch (error) {
    console.error('❌ Global integration test setup failed:', error.message);
    // Don't fail the entire test suite - individual tests will handle missing infrastructure
  }
};