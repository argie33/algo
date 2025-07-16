const crypto = require('crypto');

/**
 * Encryption/Decryption utilities for API keys
 * Used to securely store and retrieve user API keys
 */

/**
 * Decrypt an encrypted value
 * @param {string} encryptedText - The encrypted text (hex)
 * @param {string} iv - The initialization vector (hex)
 * @param {string} authTag - The authentication tag (hex)
 * @param {string} salt - The user's salt (hex)
 * @returns {string} The decrypted text
 */
function decrypt(encryptedText, iv, authTag, salt) {
  try {
    // Derive key from salt (same as used in encryption)
    const key = crypto.pbkdf2Sync(salt, Buffer.from(salt, 'hex'), 10000, 32, 'sha256');
    
    // Create decipher
    const decipher = crypto.createDecipherGCM('aes-256-gcm');
    decipher.setKey(key);
    decipher.setIV(Buffer.from(iv, 'hex'));
    decipher.setAuthTag(Buffer.from(authTag, 'hex'));
    
    // Decrypt
    let decrypted = decipher.update(encryptedText, 'hex', 'utf8');
    decrypted += decipher.final('utf8');
    
    return decrypted;
  } catch (error) {
    console.error('Decryption error:', error);
    throw new Error('Failed to decrypt API key');
  }
}

/**
 * Encrypt a value
 * @param {string} text - The text to encrypt
 * @param {string} salt - The user's salt (hex)
 * @returns {object} Object containing encrypted text, iv, and authTag
 */
function encrypt(text, salt) {
  try {
    // Derive key from salt
    const key = crypto.pbkdf2Sync(salt, Buffer.from(salt, 'hex'), 10000, 32, 'sha256');
    
    // Generate IV
    const iv = crypto.randomBytes(16);
    
    // Create cipher
    const cipher = crypto.createCipherGCM('aes-256-gcm');
    cipher.setKey(key);
    cipher.setIV(iv);
    
    // Encrypt
    let encrypted = cipher.update(text, 'utf8', 'hex');
    encrypted += cipher.final('hex');
    
    // Get auth tag
    const authTag = cipher.getAuthTag();
    
    return {
      encrypted: encrypted,
      iv: iv.toString('hex'),
      authTag: authTag.toString('hex')
    };
  } catch (error) {
    console.error('Encryption error:', error);
    throw new Error('Failed to encrypt API key');
  }
}

/**
 * Generate a random salt
 * @returns {string} Random salt as hex string
 */
function generateSalt() {
  return crypto.randomBytes(32).toString('hex');
}

module.exports = {
  decrypt,
  encrypt,
  generateSalt
};