#!/usr/bin/env node
/**
 * Secure Key Generation Utility
 * Generates cryptographically secure keys for API encryption and JWT signing
 */

const crypto = require('crypto');

/**
 * Generate a cryptographically secure API encryption key
 * @returns {string} Base64 encoded 256-bit key
 */
function generateApiEncryptionKey() {
    return crypto.randomBytes(32).toString('base64');
}

/**
 * Generate a JWT signing secret
 * @returns {string} Base64 encoded 512-bit key
 */
function generateJwtSecret() {
    return crypto.randomBytes(64).toString('base64');
}

/**
 * Generate session encryption key
 * @returns {string} Base64 encoded 256-bit key
 */
function generateSessionKey() {
    return crypto.randomBytes(32).toString('base64');
}

/**
 * Generate a secure user salt
 * @returns {string} Hex encoded 256-bit salt
 */
function generateUserSalt() {
    return crypto.randomBytes(32).toString('hex');
}

/**
 * Validate that a key has sufficient entropy
 * @param {string} key - The key to validate
 * @param {number} minBytes - Minimum bytes of entropy required
 * @returns {boolean} True if key has sufficient entropy
 */
function validateKeyEntropy(key, minBytes = 32) {
    try {
        const buffer = Buffer.from(key, 'base64');
        return buffer.length >= minBytes;
    } catch (error) {
        return false;
    }
}

/**
 * Generate all required keys for the application
 * @returns {object} Object containing all generated keys
 */
function generateAllKeys() {
    return {
        API_KEY_ENCRYPTION_SECRET: generateApiEncryptionKey(),
        JWT_SECRET: generateJwtSecret(),
        SESSION_SECRET: generateSessionKey(),
        BACKUP_API_KEY_ENCRYPTION_SECRET: generateApiEncryptionKey(),
        timestamp: new Date().toISOString(),
        entropy_info: {
            api_encryption_bits: 256,
            jwt_secret_bits: 512,
            session_secret_bits: 256
        }
    };
}

/**
 * Generate environment variables format
 * @param {object} keys - Keys object from generateAllKeys()
 * @returns {string} Environment variables format
 */
function generateEnvFormat(keys) {
    return `# Cryptographic Keys - Generated ${keys.timestamp}
# Store these securely and never commit to version control

# Primary API key encryption secret (256-bit)
API_KEY_ENCRYPTION_SECRET="${keys.API_KEY_ENCRYPTION_SECRET}"

# JWT signing secret (512-bit) - if using custom JWT implementation
JWT_SECRET="${keys.JWT_SECRET}"

# Session encryption secret (256-bit)
SESSION_SECRET="${keys.SESSION_SECRET}"

# Backup API key encryption secret for key rotation
BACKUP_API_KEY_ENCRYPTION_SECRET="${keys.BACKUP_API_KEY_ENCRYPTION_SECRET}"

# Key rotation date for tracking
KEY_GENERATION_DATE="${keys.timestamp}"
`;
}

// If run directly, generate and display keys
if (require.main === module) {
    console.log('🔐 Generating cryptographically secure keys...\n');
    
    const keys = generateAllKeys();
    
    console.log('✅ Generated keys with the following entropy:');
    console.log(`   • API Encryption Key: ${keys.entropy_info.api_encryption_bits} bits`);
    console.log(`   • JWT Secret: ${keys.entropy_info.jwt_secret_bits} bits`);
    console.log(`   • Session Secret: ${keys.entropy_info.session_secret_bits} bits\n`);
    
    console.log('📋 Environment Variables Format:');
    console.log('=====================================');
    console.log(generateEnvFormat(keys));
    
    console.log('🔒 SECURITY NOTES:');
    console.log('• Store these keys in AWS Secrets Manager or secure environment variables');
    console.log('• Never commit these keys to version control');
    console.log('• Implement key rotation every 90 days');
    console.log('• Use the backup key for seamless rotation');
    console.log('• Monitor key usage and access patterns\n');
    
    // Validate generated keys
    const validations = [
        { name: 'API Encryption', valid: validateKeyEntropy(keys.API_KEY_ENCRYPTION_SECRET, 32) },
        { name: 'JWT Secret', valid: validateKeyEntropy(keys.JWT_SECRET, 64) },
        { name: 'Session Secret', valid: validateKeyEntropy(keys.SESSION_SECRET, 32) },
        { name: 'Backup API Encryption', valid: validateKeyEntropy(keys.BACKUP_API_KEY_ENCRYPTION_SECRET, 32) }
    ];
    
    console.log('🧪 Key Validation:');
    validations.forEach(v => {
        console.log(`   ${v.valid ? '✅' : '❌'} ${v.name}: ${v.valid ? 'Valid' : 'Invalid'}`);
    });
    
    const allValid = validations.every(v => v.valid);
    console.log(`\n${allValid ? '🎉 All keys generated successfully!' : '❌ Some keys failed validation!'}`);
    
    process.exit(allValid ? 0 : 1);
}

module.exports = {
    generateApiEncryptionKey,
    generateJwtSecret,
    generateSessionKey,
    generateUserSalt,
    generateAllKeys,
    generateEnvFormat,
    validateKeyEntropy
};