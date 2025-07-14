#!/usr/bin/env node
/**
 * Create API Key Encryption Secret in AWS Secrets Manager
 * This script creates the required encryption secret for secure API key storage
 */

const { SecretsManagerClient, CreateSecretCommand, UpdateSecretCommand, DescribeSecretCommand } = require('@aws-sdk/client-secrets-manager');
const crypto = require('crypto');

const client = new SecretsManagerClient({
    region: process.env.AWS_REGION || 'us-east-1'
});

async function createApiKeyEncryptionSecret() {
    console.log('🔐 Creating API Key Encryption Secret...');
    
    try {
        // Generate a secure 256-bit encryption key
        const encryptionKey = crypto.randomBytes(32).toString('base64');
        
        const secretName = 'stocks-app/api-key-encryption';
        const secretValue = {
            API_KEY_ENCRYPTION_SECRET: encryptionKey,
            description: 'AES-256-GCM encryption key for broker API key storage',
            created: new Date().toISOString(),
            algorithm: 'AES-256-GCM'
        };
        
        // Try to check if secret already exists
        let secretExists = false;
        try {
            const describeCommand = new DescribeSecretCommand({ SecretId: secretName });
            await client.send(describeCommand);
            secretExists = true;
            console.log('⚠️  Secret already exists, updating...');
        } catch (error) {
            if (error.name !== 'ResourceNotFoundException') {
                throw error;
            }
            console.log('📝 Creating new secret...');
        }
        
        if (secretExists) {
            // Update existing secret
            const updateCommand = new UpdateSecretCommand({
                SecretId: secretName,
                SecretString: JSON.stringify(secretValue)
            });
            
            const response = await client.send(updateCommand);
            console.log('✅ API Key encryption secret updated successfully');
            console.log(`📋 Secret ARN: ${response.ARN}`);
        } else {
            // Create new secret
            const createCommand = new CreateSecretCommand({
                Name: secretName,
                Description: 'API key encryption secret for financial dashboard',
                SecretString: JSON.stringify(secretValue),
                Tags: [
                    { Key: 'Project', Value: 'financial-dashboard' },
                    { Key: 'Purpose', Value: 'api-key-encryption' },
                    { Key: 'Environment', Value: 'production' }
                ]
            });
            
            const response = await client.send(createCommand);
            console.log('✅ API Key encryption secret created successfully');
            console.log(`📋 Secret ARN: ${response.ARN}`);
        }
        
        console.log('🔑 Secret Details:');
        console.log(`   Name: ${secretName}`);
        console.log(`   Key Length: ${encryptionKey.length} characters (${crypto.randomBytes(32).length * 8} bits)`);
        console.log(`   Algorithm: AES-256-GCM`);
        
        console.log('\n💡 Next Steps:');
        console.log('1. Restart Lambda function to pick up new secret');
        console.log('2. Test API key encryption service');
        console.log('3. Verify /settings/api-keys endpoint works');
        
        return {
            secretName,
            encryptionKey,
            success: true
        };
        
    } catch (error) {
        console.error('❌ Failed to create API key encryption secret:', error);
        console.error('Error details:', error.message);
        
        if (error.code === 'InvalidParameterException') {
            console.log('💡 Try running with AWS credentials configured');
        }
        
        return {
            success: false,
            error: error.message
        };
    }
}

// Also create JWT secret if needed
async function createJwtSecret() {
    console.log('🔐 Creating JWT Secret...');
    
    try {
        const jwtKey = crypto.randomBytes(64).toString('base64');
        
        const secretName = 'stocks-app/jwt-secret';
        const secretValue = {
            JWT_SECRET: jwtKey,
            description: 'JWT signing key for authentication',
            created: new Date().toISOString(),
            algorithm: 'HS256'
        };
        
        // Try to check if secret already exists
        let secretExists = false;
        try {
            const describeCommand = new DescribeSecretCommand({ SecretId: secretName });
            await client.send(describeCommand);
            secretExists = true;
            console.log('⚠️  JWT secret already exists, updating...');
        } catch (error) {
            if (error.name !== 'ResourceNotFoundException') {
                throw error;
            }
            console.log('📝 Creating new JWT secret...');
        }
        
        if (secretExists) {
            const updateCommand = new UpdateSecretCommand({
                SecretId: secretName,
                SecretString: JSON.stringify(secretValue)
            });
            
            const response = await client.send(updateCommand);
            console.log('✅ JWT secret updated successfully');
        } else {
            const createCommand = new CreateSecretCommand({
                Name: secretName,
                Description: 'JWT secret for financial dashboard authentication',
                SecretString: JSON.stringify(secretValue),
                Tags: [
                    { Key: 'Project', Value: 'financial-dashboard' },
                    { Key: 'Purpose', Value: 'jwt-signing' },
                    { Key: 'Environment', Value: 'production' }
                ]
            });
            
            const response = await client.send(createCommand);
            console.log('✅ JWT secret created successfully');
        }
        
        return { success: true };
        
    } catch (error) {
        console.error('❌ Failed to create JWT secret:', error.message);
        return { success: false, error: error.message };
    }
}

async function main() {
    console.log('🚀 Setting up AWS Secrets for API Key Integration...\n');
    
    // Create both secrets
    const apiKeyResult = await createApiKeyEncryptionSecret();
    console.log(''); // spacing
    const jwtResult = await createJwtSecret();
    
    console.log('\n📊 RESULTS SUMMARY');
    console.log('='.repeat(50));
    console.log(`✅ API Key Encryption Secret: ${apiKeyResult.success ? 'SUCCESS' : 'FAILED'}`);
    console.log(`✅ JWT Secret: ${jwtResult.success ? 'SUCCESS' : 'FAILED'}`);
    
    if (apiKeyResult.success && jwtResult.success) {
        console.log('\n🎉 All secrets created successfully!');
        console.log('\n🔄 Next: Restart the Lambda function to load new secrets');
        console.log('   The API key service should then work properly');
    } else {
        console.log('\n⚠️  Some secrets failed to create - check errors above');
        process.exit(1);
    }
}

// Run if called directly
if (require.main === module) {
    main().catch(error => {
        console.error('Script execution failed:', error);
        process.exit(1);
    });
}

module.exports = { createApiKeyEncryptionSecret, createJwtSecret };