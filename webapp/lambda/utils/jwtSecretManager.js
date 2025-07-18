/**
 * JWT Secret Management Service
 * Manages JWT secrets for API key service token generation and validation
 */

const crypto = require('crypto');
const { SecretsManagerClient, GetSecretValueCommand, CreateSecretCommand, UpdateSecretCommand } = require('@aws-sdk/client-secrets-manager');

class JwtSecretManager {
    constructor() {
        this.secretsManager = new SecretsManagerClient({
            region: process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || 'us-east-1'
        });
        
        this.jwtSecret = null;
        this.jwtSecretCache = null;
        this.initPromise = null;
    }

    /**
     * Initialize JWT secret management
     */
    async initialize() {
        if (this.initPromise) {
            return this.initPromise;
        }

        this.initPromise = this._loadOrCreateJwtSecret();
        return this.initPromise;
    }

    /**
     * Load existing JWT secret or create a new one
     */
    async _loadOrCreateJwtSecret() {
        try {
            console.log('🔐 Initializing JWT secret management...');

            // First try to load from environment (for local development)
            if (process.env.JWT_SECRET) {
                console.log('🔧 Using JWT secret from environment variable');
                this.jwtSecret = process.env.JWT_SECRET;
                this.jwtSecretCache = this.jwtSecret;
                return this.jwtSecret;
            }

            // Try to load from AWS Secrets Manager
            const secretArn = process.env.JWT_SECRET_ARN;
            if (secretArn) {
                console.log('📡 Loading JWT secret from AWS Secrets Manager...');
                const secret = await this._loadSecretFromSecretsManager(secretArn);
                if (secret) {
                    this.jwtSecret = secret;
                    this.jwtSecretCache = secret;
                    console.log('✅ JWT secret loaded from Secrets Manager');
                    return secret;
                }
            }

            // If no ARN provided, try default secret name
            const defaultSecretName = `stocks-app-jwt-secret-${process.env.NODE_ENV || 'dev'}`;
            console.log(`🔍 Attempting to load JWT secret with default name: ${defaultSecretName}`);
            
            const existingSecret = await this._loadSecretFromSecretsManager(defaultSecretName);
            if (existingSecret) {
                this.jwtSecret = existingSecret;
                this.jwtSecretCache = existingSecret;
                console.log('✅ JWT secret loaded from default secret name');
                return existingSecret;
            }

            // Create new JWT secret if none exists
            console.log('🆕 No existing JWT secret found, creating new one...');
            const newSecret = await this._createNewJwtSecret(defaultSecretName);
            
            this.jwtSecret = newSecret;
            this.jwtSecretCache = newSecret;
            console.log('✅ New JWT secret created and cached');
            
            return newSecret;

        } catch (error) {
            console.error('❌ Failed to initialize JWT secret:', error.message);
            
            // Fallback for development: generate temporary secret
            if (process.env.NODE_ENV !== 'production') {
                console.warn('⚠️ Using temporary JWT secret for development');
                const tempSecret = crypto.randomBytes(64).toString('hex');
                this.jwtSecret = tempSecret;
                this.jwtSecretCache = tempSecret;
                return tempSecret;
            }
            
            throw new Error(`JWT secret initialization failed: ${error.message}`);
        }
    }

    /**
     * Load secret from AWS Secrets Manager
     */
    async _loadSecretFromSecretsManager(secretId) {
        try {
            const command = new GetSecretValueCommand({ SecretId: secretId });
            const response = await this.secretsManager.send(command);
            
            if (!response.SecretString) {
                throw new Error('Secret value is empty');
            }

            // Try to parse as JSON first
            try {
                const secretData = JSON.parse(response.SecretString);
                return secretData.JWT_SECRET || secretData.secret || secretData.value;
            } catch (parseError) {
                // If not JSON, use as plain string
                return response.SecretString;
            }

        } catch (error) {
            if (error.name === 'ResourceNotFoundException') {
                console.log(`📝 Secret not found: ${secretId}`);
                return null;
            }
            throw error;
        }
    }

    /**
     * Create new JWT secret in AWS Secrets Manager
     */
    async _createNewJwtSecret(secretName) {
        try {
            // Generate cryptographically secure secret
            const jwtSecret = crypto.randomBytes(64).toString('hex');
            
            const secretData = {
                JWT_SECRET: jwtSecret,
                created_at: new Date().toISOString(),
                purpose: 'API key service JWT token signing',
                algorithm: 'HS256',
                key_length: jwtSecret.length
            };

            const createCommand = new CreateSecretCommand({
                Name: secretName,
                Description: `JWT secret for stocks app API key service (${process.env.NODE_ENV || 'dev'})`,
                SecretString: JSON.stringify(secretData),
                Tags: [
                    { Key: 'Application', Value: 'stocks-app' },
                    { Key: 'Component', Value: 'api-key-service' },
                    { Key: 'Environment', Value: process.env.NODE_ENV || 'dev' },
                    { Key: 'Purpose', Value: 'jwt-signing' }
                ]
            });

            const response = await this.secretsManager.send(createCommand);
            console.log(`✅ Created new JWT secret: ${response.ARN}`);
            
            // Set environment variable for future use
            if (!process.env.JWT_SECRET_ARN) {
                console.log(`💡 Consider setting JWT_SECRET_ARN=${response.ARN} in your environment`);
            }

            return jwtSecret;

        } catch (error) {
            console.error('❌ Failed to create JWT secret:', error.message);
            throw error;
        }
    }

    /**
     * Get JWT secret (cached)
     */
    async getJwtSecret() {
        if (!this.jwtSecretCache) {
            await this.initialize();
        }
        
        if (!this.jwtSecretCache) {
            throw new Error('JWT secret not available');
        }
        
        return this.jwtSecretCache;
    }

    /**
     * Rotate JWT secret (creates new secret and updates Secrets Manager)
     */
    async rotateJwtSecret() {
        try {
            console.log('🔄 Starting JWT secret rotation...');
            
            const newSecret = crypto.randomBytes(64).toString('hex');
            const secretName = process.env.JWT_SECRET_ARN || `stocks-app-jwt-secret-${process.env.NODE_ENV || 'dev'}`;
            
            const secretData = {
                JWT_SECRET: newSecret,
                rotated_at: new Date().toISOString(),
                previous_secret_hash: crypto.createHash('sha256').update(this.jwtSecretCache || '').digest('hex').substring(0, 16),
                purpose: 'API key service JWT token signing',
                algorithm: 'HS256',
                key_length: newSecret.length
            };

            const updateCommand = new UpdateSecretCommand({
                SecretId: secretName,
                SecretString: JSON.stringify(secretData)
            });

            await this.secretsManager.send(updateCommand);
            
            // Update cache
            this.jwtSecretCache = newSecret;
            this.jwtSecret = newSecret;
            
            console.log('✅ JWT secret rotated successfully');
            return newSecret;

        } catch (error) {
            console.error('❌ JWT secret rotation failed:', error.message);
            throw error;
        }
    }

    /**
     * Validate JWT secret strength
     */
    validateSecretStrength(secret) {
        if (!secret || typeof secret !== 'string') {
            return {
                valid: false,
                reason: 'Secret is empty or not a string',
                recommendations: ['Provide a valid string secret']
            };
        }

        if (secret.length < 32) {
            return {
                valid: false,
                reason: 'Secret is too short (minimum 32 characters)',
                recommendations: ['Use at least 32 characters for security', 'Consider using 64+ characters for production']
            };
        }

        if (secret.length < 64) {
            return {
                valid: true,
                warnings: ['Consider using 64+ characters for enhanced security'],
                strength: 'adequate'
            };
        }

        // Check for entropy (not just repeated characters)
        const uniqueChars = new Set(secret).size;
        const entropyRatio = uniqueChars / secret.length;
        
        if (entropyRatio < 0.5) {
            return {
                valid: true,
                warnings: ['Secret has low entropy (many repeated characters)', 'Consider using crypto.randomBytes() for generation'],
                strength: 'low_entropy'
            };
        }

        return {
            valid: true,
            strength: 'strong',
            entropy: entropyRatio,
            length: secret.length
        };
    }

    /**
     * Get JWT secret information (without revealing the secret)
     */
    async getSecretInfo() {
        try {
            await this.initialize();
            
            const validation = this.validateSecretStrength(this.jwtSecretCache);
            
            return {
                available: !!this.jwtSecretCache,
                source: process.env.JWT_SECRET ? 'environment' : 'secrets_manager',
                length: this.jwtSecretCache ? this.jwtSecretCache.length : 0,
                validation: validation,
                lastInitialized: new Date().toISOString()
            };

        } catch (error) {
            return {
                available: false,
                error: error.message,
                source: 'unknown'
            };
        }
    }

    /**
     * Clear cached secret (force reload on next access)
     */
    clearCache() {
        this.jwtSecretCache = null;
        this.jwtSecret = null;
        this.initPromise = null;
        console.log('🧹 JWT secret cache cleared');
    }
}

// Export singleton instance
const jwtSecretManager = new JwtSecretManager();

module.exports = jwtSecretManager;