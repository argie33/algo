// Centralized Secrets Management for Lambda
// Loads required secrets from AWS Secrets Manager and injects into process.env
// This ensures all Lambda functions have access to required environment variables

const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');

class SecretsLoader {
  constructor() {
    this.client = new SecretsManagerClient({
      region: process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || 'us-east-1'
    });
    this.secretsCache = new Map();
    this.initialized = false;
  }

  async loadAllSecrets() {
    if (this.initialized) {
      console.log('✅ Secrets already loaded');
      return;
    }

    console.log('🔐 Loading application secrets...');
    const startTime = Date.now();

    try {
      // Load core application secrets
      await this.loadCoreSecrets();
      
      // Load API key encryption secret
      await this.loadApiKeyEncryptionSecret();
      
      // Load JWT secrets
      await this.loadJwtSecrets();
      
      this.initialized = true;
      console.log(`✅ All secrets loaded successfully in ${Date.now() - startTime}ms`);
      
    } catch (error) {
      console.error('❌ Failed to load secrets:', error.message);
      console.warn('⚠️  Application will run with limited functionality');
      
      // Set fallback values for development/testing
      this.setFallbackSecrets();
    }
  }

  async loadCoreSecrets() {
    try {
      // Try to get the main application secrets
      const secretArn = process.env.DB_SECRET_ARN;
      if (secretArn) {
        console.log('🔑 Loading database secrets...');
        const dbSecrets = await this.getSecret(secretArn);
        
        // Database secrets are already handled by database.js
        // Just validate they're accessible
        if (dbSecrets) {
          console.log('✅ Database secrets accessible');
        }
      }
    } catch (error) {
      console.warn('⚠️  Database secrets not available:', error.message);
    }
  }

  async loadApiKeyEncryptionSecret() {
    try {
      console.log('🔐 Loading API key encryption secret...');
      
      // Try multiple possible secret locations (CloudFormation naming first)
      const possibleSecrets = [
        'stocks-app-api-key-encryption-stocks-app-stack',
        'stocks-app-api-key-encryption-dev',
        'stocks-app/api-key-encryption',
        'stocks/api-key-encryption',
        'financial-dashboard/encryption-key',
        'webapp/api-encryption-secret'
      ];

      let encryptionSecret = null;
      
      for (const secretName of possibleSecrets) {
        try {
          const secret = await this.getSecret(secretName);
          if (secret) {
            if (typeof secret === 'string') {
              encryptionSecret = secret;
            } else if (secret.API_KEY_ENCRYPTION_SECRET) {
              encryptionSecret = secret.API_KEY_ENCRYPTION_SECRET;
            } else if (secret.encryptionKey) {
              encryptionSecret = secret.encryptionKey;
            } else if (secret.secretKey) {
              encryptionSecret = secret.secretKey;
            }
            
            if (encryptionSecret) {
              console.log(`✅ Found encryption secret in: ${secretName}`);
              break;
            }
          }
        } catch (err) {
          console.log(`🔍 Secret not found: ${secretName}`);
          continue;
        }
      }

      if (encryptionSecret) {
        process.env.API_KEY_ENCRYPTION_SECRET = encryptionSecret;
        console.log('✅ API key encryption secret loaded and injected');
      } else {
        console.warn('⚠️  No API key encryption secret found - generating temporary key');
        await this.generateTempEncryptionKey();
      }
      
    } catch (error) {
      console.error('❌ Failed to load API key encryption secret:', error.message);
      await this.generateTempEncryptionKey();
    }
  }

  async loadJwtSecrets() {
    try {
      console.log('🔐 Loading JWT secrets...');
      
      const possibleJwtSecrets = [
        'stocks-app-jwt-secret-stocks-app-stack',
        'stocks-app-jwt-secret-dev',
        'stocks-app/jwt-secret',
        'stocks/jwt-secret',
        'financial-dashboard/jwt-key',
        'webapp/jwt-secret'
      ];

      let jwtSecret = null;
      
      for (const secretName of possibleJwtSecrets) {
        try {
          const secret = await this.getSecret(secretName);
          if (secret) {
            if (typeof secret === 'string') {
              jwtSecret = secret;
            } else if (secret.JWT_SECRET) {
              jwtSecret = secret.JWT_SECRET;
            } else if (secret.jwtSecret) {
              jwtSecret = secret.jwtSecret;
            }
            
            if (jwtSecret) {
              console.log(`✅ Found JWT secret in: ${secretName}`);
              break;
            }
          }
        } catch (err) {
          continue;
        }
      }

      if (jwtSecret) {
        process.env.JWT_SECRET = jwtSecret;
        console.log('✅ JWT secret loaded and injected');
      } else {
        console.warn('⚠️  No JWT secret found - using existing environment value');
      }
      
    } catch (error) {
      console.warn('⚠️  Failed to load JWT secret:', error.message);
    }
  }

  async getSecret(secretId) {
    try {
      // Check cache first
      if (this.secretsCache.has(secretId)) {
        return this.secretsCache.get(secretId);
      }

      const command = new GetSecretValueCommand({ SecretId: secretId });
      const response = await this.client.send(command);
      
      let secret;
      if (response.SecretString) {
        try {
          secret = JSON.parse(response.SecretString);
        } catch (parseError) {
          secret = response.SecretString; // Plain string secret
        }
      } else if (response.SecretBinary) {
        secret = Buffer.from(response.SecretBinary, 'base64').toString('utf-8');
      }
      
      // Cache the secret
      this.secretsCache.set(secretId, secret);
      
      return secret;
    } catch (error) {
      if (error.name === 'ResourceNotFoundException') {
        console.log(`🔍 Secret not found: ${secretId}`);
      } else {
        console.error(`❌ Error getting secret ${secretId}:`, error.message);
      }
      return null;
    }
  }

  async generateTempEncryptionKey() {
    console.log('🔄 Generating temporary encryption key for this session...');
    
    // Generate a cryptographically secure temporary key
    const crypto = require('crypto');
    const tempKey = crypto.randomBytes(32).toString('hex');
    
    process.env.API_KEY_ENCRYPTION_SECRET = tempKey;
    process.env.TEMP_ENCRYPTION_KEY = 'true';
    
    console.log('⚠️  Using temporary encryption key - API keys will only work for this session');
    console.log('💡 To fix permanently: Create a secret named "stocks-app/api-key-encryption" in AWS Secrets Manager');
  }

  setFallbackSecrets() {
    console.log('🔄 Setting fallback secrets for limited functionality...');
    
    // Only set if not already present
    if (!process.env.API_KEY_ENCRYPTION_SECRET) {
      const crypto = require('crypto');
      process.env.API_KEY_ENCRYPTION_SECRET = crypto.randomBytes(32).toString('hex');
      process.env.TEMP_ENCRYPTION_KEY = 'true';
      console.log('⚠️  Using temporary encryption key');
    }
    
    if (!process.env.JWT_SECRET) {
      const crypto = require('crypto');
      process.env.JWT_SECRET = crypto.randomBytes(32).toString('hex');
      process.env.TEMP_JWT_SECRET = 'true';
      console.log('⚠️  Using temporary JWT secret');
    }
  }

  // Helper method to check if secrets are loaded
  isInitialized() {
    return this.initialized;
  }

  // Helper method to check if using temporary secrets
  isUsingTempSecrets() {
    return process.env.TEMP_ENCRYPTION_KEY === 'true' || process.env.TEMP_JWT_SECRET === 'true';
  }

  // Get initialization status for debugging
  getStatus() {
    return {
      initialized: this.initialized,
      hasApiKeyEncryption: !!process.env.API_KEY_ENCRYPTION_SECRET,
      hasJwtSecret: !!process.env.JWT_SECRET,
      usingTempEncryption: process.env.TEMP_ENCRYPTION_KEY === 'true',
      usingTempJwt: process.env.TEMP_JWT_SECRET === 'true',
      cachedSecrets: this.secretsCache.size
    };
  }
}

// Create singleton instance
const secretsLoader = new SecretsLoader();

module.exports = secretsLoader;