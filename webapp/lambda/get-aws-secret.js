// AWS Secrets Manager test script
const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');
require('dotenv').config();

async function getSecret() {
  const client = new SecretsManagerClient({
    region: process.env.AWS_REGION || 'us-east-1'
  });

  try {
    console.log('🔑 Attempting to get secret:', process.env.DB_SECRET_ARN);
    
    const command = new GetSecretValueCommand({
      SecretId: process.env.DB_SECRET_ARN
    });

    const response = await client.send(command);
    
    if (response.SecretString) {
      const secret = JSON.parse(response.SecretString);
      console.log('✅ Secret retrieved successfully:');
      console.log('Host:', secret.host || secret.endpoint);
      console.log('Port:', secret.port);
      console.log('Database:', secret.dbname || secret.database);
      console.log('Username:', secret.username || secret.user);
      console.log('Password:', secret.password ? '[REDACTED]' : 'NOT SET');
      return secret;
    } else {
      throw new Error('Secret value is empty');
    }
  } catch (error) {
    console.error('❌ Failed to get secret:', error.message);
    if (error.name === 'UnrecognizedClientException') {
      console.error('🔧 Check AWS credentials configuration');
    }
    if (error.name === 'ResourceNotFoundException') {
      console.error('🔧 Secret ARN may be incorrect or not exist');
    }
  }
}

getSecret();