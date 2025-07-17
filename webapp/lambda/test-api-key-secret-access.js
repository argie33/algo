// Test API Key Encryption Secret Access
console.log('=== API KEY ENCRYPTION SECRET ACCESS TEST ===');

// Test environment variables
console.log('Environment Variables:');
console.log('NODE_ENV:', process.env.NODE_ENV);
console.log('AWS_REGION:', process.env.AWS_REGION);
console.log('WEBAPP_AWS_REGION:', process.env.WEBAPP_AWS_REGION);
console.log('API_KEY_ENCRYPTION_SECRET_ARN:', process.env.API_KEY_ENCRYPTION_SECRET_ARN ? 'present' : 'missing');

// Test AWS SDK access
try {
  const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');
  
  // Test client initialization
  const secretsManager = new SecretsManagerClient({
    region: process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || 'us-east-1'
  });
  
  console.log('✅ SecretsManagerClient initialized successfully');
  
  // Test secret access (async function)
  async function testSecretAccess() {
    try {
      const secretArn = process.env.API_KEY_ENCRYPTION_SECRET_ARN;
      if (!secretArn) {
        console.log('❌ API_KEY_ENCRYPTION_SECRET_ARN environment variable not set');
        return;
      }
      
      console.log('🔐 Testing secret access for:', secretArn);
      
      const command = new GetSecretValueCommand({ SecretId: secretArn });
      const response = await secretsManager.send(command);
      
      if (!response.SecretString) {
        console.log('❌ Secret value is empty');
        return;
      }
      
      // Parse the secret
      const secretData = JSON.parse(response.SecretString);
      console.log('✅ Secret retrieved successfully');
      console.log('Secret keys:', Object.keys(secretData));
      
      // Check for the specific key
      const encryptionKey = secretData.API_KEY_ENCRYPTION_SECRET;
      if (encryptionKey) {
        console.log('✅ API_KEY_ENCRYPTION_SECRET found in secret data');
        console.log('Key length:', encryptionKey.length, 'characters');
      } else {
        console.log('❌ API_KEY_ENCRYPTION_SECRET not found in secret data');
        console.log('Available keys:', Object.keys(secretData));
      }
      
    } catch (error) {
      console.error('❌ Error accessing secret:', error.message);
      console.error('Error details:', error);
    }
  }
  
  // Run the test
  testSecretAccess().then(() => {
    console.log('=== SECRET ACCESS TEST COMPLETE ===');
  });
  
} catch (error) {
  console.error('❌ Failed to initialize AWS SDK:', error);
}

// Create a simple Lambda handler for testing
exports.handler = async (event, context) => {
  console.log('Lambda handler called for API key secret test');
  
  const result = {
    statusCode: 200,
    headers: {
      'Content-Type': 'application/json',
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization'
    },
    body: JSON.stringify({
      success: true,
      message: 'API key secret access test',
      environment: {
        NODE_ENV: process.env.NODE_ENV,
        AWS_REGION: process.env.AWS_REGION,
        WEBAPP_AWS_REGION: process.env.WEBAPP_AWS_REGION,
        hasApiKeySecretArn: !!process.env.API_KEY_ENCRYPTION_SECRET_ARN
      },
      timestamp: new Date().toISOString()
    })
  };
  
  return result;
};