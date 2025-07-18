#!/usr/bin/env node

/**
 * Create Encryption Secrets Script
 * Generates and stores proper encryption secrets for production use
 */

const crypto = require('crypto');
const { SecretsManagerClient, CreateSecretCommand, GetSecretValueCommand, UpdateSecretCommand } = require('@aws-sdk/client-secrets-manager');

const secretsManager = new SecretsManagerClient({
    region: process.env.AWS_REGION || 'us-east-1'
});

/**
 * Generate cryptographically secure secrets
 */
function generateSecrets() {
    return {
        apiKeyEncryptionSecret: crypto.randomBytes(64).toString('hex'),
        jwtSecret: crypto.randomBytes(64).toString('hex'),
        sessionSecret: crypto.randomBytes(32).toString('hex'),
        csrfSecret: crypto.randomBytes(32).toString('hex')
    };
}

/**
 * Create or update API key encryption secret
 */
async function createApiKeyEncryptionSecret(environment = 'dev') {
    try {
        const secretName = `stocks-app-api-key-encryption-${environment}`;
        const secrets = generateSecrets();
        
        const secretData = {
            API_KEY_ENCRYPTION_SECRET: secrets.apiKeyEncryptionSecret,
            created_at: new Date().toISOString(),
            environment: environment,
            purpose: 'API key encryption for user credentials',
            algorithm: 'AES-256-GCM',
            key_length: secrets.apiKeyEncryptionSecret.length,
            security_notes: [
                'This secret is used to encrypt user API keys in the database',
                'Changing this secret will invalidate all existing encrypted API keys',
                'Store this secret securely and rotate periodically'
            ]
        };

        // Check if secret already exists
        try {
            await secretsManager.send(new GetSecretValueCommand({ SecretId: secretName }));
            console.log(`⚠️ Secret ${secretName} already exists. Use --force to update.`);
            
            if (!process.argv.includes('--force')) {
                console.log('Use: node createEncryptionSecrets.js --force to update existing secrets');
                return null;
            }
            
            // Update existing secret
            const updateResponse = await secretsManager.send(new UpdateSecretCommand({
                SecretId: secretName,
                SecretString: JSON.stringify(secretData),
                Description: `API key encryption secret for stocks app (${environment})`
            }));
            
            console.log(`✅ Updated API key encryption secret: ${secretName}`);
            return updateResponse.ARN;
            
        } catch (error) {
            if (error.name === 'ResourceNotFoundException') {
                // Create new secret
                const createResponse = await secretsManager.send(new CreateSecretCommand({
                    Name: secretName,
                    Description: `API key encryption secret for stocks app (${environment})`,
                    SecretString: JSON.stringify(secretData),
                    Tags: [
                        { Key: 'Application', Value: 'stocks-app' },
                        { Key: 'Component', Value: 'api-key-service' },
                        { Key: 'Environment', Value: environment },
                        { Key: 'Purpose', Value: 'encryption' },
                        { Key: 'CreatedBy', Value: 'createEncryptionSecrets.js' }
                    ]
                }));
                
                console.log(`✅ Created API key encryption secret: ${secretName}`);
                console.log(`📝 ARN: ${createResponse.ARN}`);
                return createResponse.ARN;
            }
            throw error;
        }
    } catch (error) {
        console.error('❌ Failed to create API key encryption secret:', error.message);
        throw error;
    }
}

/**
 * Create or update JWT secret
 */
async function createJwtSecret(environment = 'dev') {
    try {
        const secretName = `stocks-app-jwt-secret-${environment}`;
        const secrets = generateSecrets();
        
        const secretData = {
            JWT_SECRET: secrets.jwtSecret,
            SESSION_SECRET: secrets.sessionSecret,
            CSRF_SECRET: secrets.csrfSecret,
            created_at: new Date().toISOString(),
            environment: environment,
            purpose: 'JWT token signing and session management',
            algorithm: 'HS256',
            key_length: secrets.jwtSecret.length,
            security_notes: [
                'JWT_SECRET is used for signing API key service tokens',
                'SESSION_SECRET is used for session management',
                'CSRF_SECRET is used for CSRF protection',
                'Rotate these secrets periodically for security'
            ]
        };

        // Check if secret already exists
        try {
            await secretsManager.send(new GetSecretValueCommand({ SecretId: secretName }));
            console.log(`⚠️ Secret ${secretName} already exists. Use --force to update.`);
            
            if (!process.argv.includes('--force')) {
                return null;
            }
            
            // Update existing secret
            const updateResponse = await secretsManager.send(new UpdateSecretCommand({
                SecretId: secretName,
                SecretString: JSON.stringify(secretData),
                Description: `JWT secrets for stocks app (${environment})`
            }));
            
            console.log(`✅ Updated JWT secret: ${secretName}`);
            return updateResponse.ARN;
            
        } catch (error) {
            if (error.name === 'ResourceNotFoundException') {
                // Create new secret
                const createResponse = await secretsManager.send(new CreateSecretCommand({
                    Name: secretName,
                    Description: `JWT secrets for stocks app (${environment})`,
                    SecretString: JSON.stringify(secretData),
                    Tags: [
                        { Key: 'Application', Value: 'stocks-app' },
                        { Key: 'Component', Value: 'auth-service' },
                        { Key: 'Environment', Value: environment },
                        { Key: 'Purpose', Value: 'jwt-signing' },
                        { Key: 'CreatedBy', Value: 'createEncryptionSecrets.js' }
                    ]
                }));
                
                console.log(`✅ Created JWT secret: ${secretName}`);
                console.log(`📝 ARN: ${createResponse.ARN}`);
                return createResponse.ARN;
            }
            throw error;
        }
    } catch (error) {
        console.error('❌ Failed to create JWT secret:', error.message);
        throw error;
    }
}

/**
 * Generate environment variables template
 */
function generateEnvTemplate(apiKeyArn, jwtArn, environment) {
    return `
# ${environment.toUpperCase()} Environment Variables for Stocks App
# Generated on ${new Date().toISOString()}

# API Key Encryption
API_KEY_ENCRYPTION_SECRET_ARN=${apiKeyArn}

# JWT Secrets
JWT_SECRET_ARN=${jwtArn}

# Environment
NODE_ENV=${environment}
AWS_REGION=${process.env.AWS_REGION || 'us-east-1'}

# Database (configure separately)
# DB_SECRET_ARN=arn:aws:secretsmanager:region:account:secret:db-secret-name

# Cognito (configure separately) 
# COGNITO_USER_POOL_ID=us-east-1_xxxxxxxxx
# COGNITO_CLIENT_ID=xxxxxxxxx
# COGNITO_SECRET_ARN=arn:aws:secretsmanager:region:account:secret:cognito-secret-name
`;
}

/**
 * Main execution function
 */
async function main() {
    console.log('🔐 Creating encryption secrets for Stocks App...');
    
    const environment = process.argv[2] || process.env.NODE_ENV || 'dev';
    const force = process.argv.includes('--force');
    
    console.log(`📋 Environment: ${environment}`);
    console.log(`🔄 Force update: ${force}`);
    console.log('');
    
    try {
        // Create API key encryption secret
        console.log('1️⃣ Creating API key encryption secret...');
        const apiKeyArn = await createApiKeyEncryptionSecret(environment);
        
        // Create JWT secret
        console.log('2️⃣ Creating JWT secret...');
        const jwtArn = await createJwtSecret(environment);
        
        // Generate environment template
        if (apiKeyArn || jwtArn) {
            console.log('');
            console.log('📝 Environment Variables Template:');
            console.log('=' .repeat(60));
            console.log(generateEnvTemplate(apiKeyArn, jwtArn, environment));
            console.log('=' .repeat(60));
            console.log('');
            console.log('💡 Next Steps:');
            console.log('1. Add these environment variables to your deployment configuration');
            console.log('2. Update your CloudFormation templates with the secret ARNs');
            console.log('3. Restart your Lambda functions to pick up the new secrets');
            console.log('4. Test the API key service health endpoint');
        }
        
        console.log('✅ Encryption secrets setup completed successfully!');
        
    } catch (error) {
        console.error('❌ Setup failed:', error.message);
        process.exit(1);
    }
}

// Run if called directly
if (require.main === module) {
    main().catch(console.error);
}

module.exports = {
    generateSecrets,
    createApiKeyEncryptionSecret,
    createJwtSecret,
    generateEnvTemplate
};