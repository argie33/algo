/**
 * Token Blocklist Manager
 * SECURITY FIX #7: Implements JWT revocation via in-memory blocklist
 *
 * Uses in-memory blocklist within Lambda container (sufficient for most cases).
 * Tokens naturally expire via JWT exp claim, so revocation is a best-effort
 * invalidation before expiration (handles immediate logout before token expires).
 *
 * Note: For distributed revocation across instances, use DynamoDB
 * (can be added as future enhancement).
 */

const logger = require("./logger");

// In-memory blocklist of revoked tokens
// Maps token_jti -> expiration_timestamp
const REVOKED_TOKENS = new Map();

// Cleanup interval for expired tokens (5 minutes)
const CLEANUP_INTERVAL = 5 * 60 * 1000;

/**
 * Clean up tokens that have naturally expired
 */
const cleanupExpiredTokens = () => {
  const now = Math.floor(Date.now() / 1000);
  let cleaned = 0;

  for (const [jti, expiration] of REVOKED_TOKENS.entries()) {
    if (expiration < now) {
      REVOKED_TOKENS.delete(jti);
      cleaned++;
    }
  }

  if (cleaned > 0) {
    logger.debug("[TOKEN_CLEANUP]", {
      cleaned,
      remaining: REVOKED_TOKENS.size,
    });
  }
};

// Start cleanup timer (runs once per container lifetime)
setInterval(cleanupExpiredTokens, CLEANUP_INTERVAL);

/**
 * Check if a token has been revoked
 * @param {string} tokenJti - JWT jti claim (unique token ID)
 * @param {number} tokenExp - JWT exp claim (expiration timestamp)
 * @returns {Promise<boolean>} - true if token is revoked/blocked
 */
const isTokenRevoked = async (tokenJti, _tokenExp) => {
  if (!tokenJti) {
    // No jti claim - cannot track revocation
    // (Some JWT implementations don't include jti)
    return false;
  }

  const isRevoked = REVOKED_TOKENS.has(tokenJti);

  if (isRevoked) {
    logger.debug("[TOKEN_REVOCATION_CHECK]", {
      jti: tokenJti.substring(0, 8),
      revoked: true,
    });
  }

  return isRevoked;
};

/**
 * Revoke a token (add to blocklist)
 * @param {string} tokenJti - JWT jti claim (unique token ID)
 * @param {number} tokenExp - JWT exp claim (expiration timestamp)
 * @returns {Promise<boolean>} - true if revocation succeeded
 */
const revokeToken = async (tokenJti, tokenExp) => {
  if (!tokenJti) {
    logger.warn("[LOGOUT] Token has no jti claim - revocation not possible");
    return false;
  }

  // Add to blocklist
  REVOKED_TOKENS.set(tokenJti, tokenExp);

  logger.info("[LOGOUT_TOKEN_REVOKED]", {
    jti: tokenJti.substring(0, 8),
    expiresAt: new Date(tokenExp * 1000).toISOString(),
    blocklistSize: REVOKED_TOKENS.size,
  });

  return true;
};

module.exports = {
  isTokenRevoked,
  revokeToken,
};
