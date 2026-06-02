/**
 * Token Blocklist Manager
 * SECURITY FIX #7: Implements JWT revocation via blocklist
 *
 * In distributed systems (Lambda), blocklist is stored in DynamoDB with TTL
 * to ensure consistency across instances.
 */

const AWS = require('aws-sdk');
const logger = require('./logger');

const dynamodb = new AWS.DynamoDB.DocumentClient({
  region: process.env.AWS_REGION || 'us-east-1',
  maxRetries: 1,
});

// In-memory cache of blocklisted tokens (for speed, with TTL)
// Maps token_jti -> expiration_timestamp
const IN_MEMORY_BLOCKLIST = new Map();
const BLOCKLIST_CHECK_INTERVAL = 5 * 60 * 1000; // 5 minutes to sync with DB

/**
 * Clean up expired tokens from in-memory cache
 */
const cleanupExpiredTokens = () => {
  const now = Date.now() / 1000;
  for (const [jti, expiration] of IN_MEMORY_BLOCKLIST.entries()) {
    if (expiration < now) {
      IN_MEMORY_BLOCKLIST.delete(jti);
    }
  }
};

// Run cleanup periodically
setInterval(cleanupExpiredTokens, BLOCKLIST_CHECK_INTERVAL);

/**
 * Check if a token has been revoked
 * @param {string} tokenJti - JWT jti claim (unique token ID)
 * @param {number} tokenExp - JWT exp claim (expiration timestamp)
 * @returns {Promise<boolean>} - true if token is revoked/blocked
 */
const isTokenRevoked = async (tokenJti, tokenExp) => {
  if (!tokenJti) {
    // No jti claim - cannot track revocation, assume valid
    // (This is a limitation of Cognito, which may not include jti)
    return false;
  }

  // Check in-memory cache first (fast path)
  if (IN_MEMORY_BLOCKLIST.has(tokenJti)) {
    return true;
  }

  // Check DynamoDB (slow path, for cross-instance consistency)
  const tableName = process.env.TOKEN_BLOCKLIST_TABLE;
  if (!tableName) {
    logger.warn('[TOKEN_REVOCATION] TOKEN_BLOCKLIST_TABLE not configured - revocation disabled');
    return false;
  }

  try {
    const result = await dynamodb.get({
      TableName: tableName,
      Key: { jti: tokenJti },
    }).promise();

    const isRevoked = !!result.Item;

    // Add to in-memory cache for future checks
    if (isRevoked) {
      IN_MEMORY_BLOCKLIST.set(tokenJti, tokenExp);
    }

    return isRevoked;
  } catch (err) {
    logger.error('[TOKEN_REVOCATION_ERROR]', {
      error: err.message,
      table: tableName,
    });
    // Fail open: if we can't check blocklist, allow the token
    // (better than breaking login for everyone)
    return false;
  }
};

/**
 * Revoke a token (add to blocklist)
 * @param {string} tokenJti - JWT jti claim (unique token ID)
 * @param {number} tokenExp - JWT exp claim (expiration timestamp)
 * @returns {Promise<boolean>} - true if revocation succeeded
 */
const revokeToken = async (tokenJti, tokenExp) => {
  if (!tokenJti) {
    logger.warn('[LOGOUT] Token has no jti claim - revocation not possible');
    return false;
  }

  // Add to in-memory cache immediately
  IN_MEMORY_BLOCKLIST.set(tokenJti, tokenExp);

  // Persist to DynamoDB for cross-instance consistency
  const tableName = process.env.TOKEN_BLOCKLIST_TABLE;
  if (!tableName) {
    logger.warn('[LOGOUT] TOKEN_BLOCKLIST_TABLE not configured - only in-memory revocation available');
    return false;
  }

  try {
    await dynamodb.put({
      TableName: tableName,
      Item: {
        jti: tokenJti,
        revokedAt: Math.floor(Date.now() / 1000),
        expiresAt: tokenExp, // TTL attribute (DynamoDB will auto-delete after expiration)
      },
      // TTL attribute name for DynamoDB
      TimeToLiveAttributeName: 'expiresAt',
    }).promise();

    logger.info('[LOGOUT_SUCCESS]', { jti: tokenJti.substring(0, 8) });
    return true;
  } catch (err) {
    logger.error('[LOGOUT_ERROR]', {
      error: err.message,
      table: tableName,
    });
    return false;
  }
};

module.exports = {
  isTokenRevoked,
  revokeToken,
};
