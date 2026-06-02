/**
 * SECURITY FIX #7: Logout Route
 * Implements JWT revocation via token blocklist
 */

const express = require('express');
const { authenticateToken } = require('../middleware/auth');
const { sendSuccess, sendError } = require('../utils/apiResponse');
const logger = require('../utils/logger');
const { revokeToken } = require('../utils/tokenBlocklist');

const router = express.Router();

/**
 * POST /api/logout
 * Revoke the current JWT token by adding it to the blocklist
 * Requires authentication
 */
router.post('/', authenticateToken, async (req, res) => {
  try {
    const user = req.user;
    const token = req.token;

    if (!user || !token) {
      return sendError(res, 'Invalid authentication state', 400, { code: 'INVALID_STATE' });
    }

    // Extract token identifier (jti claim or use token_use as fallback)
    const tokenJti = user.jti || user.token_use;
    const tokenExp = user.exp;

    if (!tokenJti) {
      logger.warn('[LOGOUT] Token lacks jti claim - cannot revoke via blocklist', {
        userId: user.sub,
        token_type: user.token_use,
      });
      // Still return success to client - they've called logout
      return sendSuccess(res, {
        success: true,
        message: 'Logged out successfully (token blocklist unavailable)',
      });
    }

    // Revoke the token
    const revoked = await revokeToken(tokenJti, tokenExp);

    logger.info('[LOGOUT_COMPLETE]', {
      userId: user.sub,
      username: user.username,
      revoked,
      ip: req.ip || req.connection.remoteAddress,
    });

    return sendSuccess(res, {
      success: true,
      message: revoked
        ? 'Logged out successfully'
        : 'Logged out (token revocation unavailable)',
      revoked,
    });
  } catch (error) {
    logger.error('[LOGOUT_ERROR]', {
      error: error.message,
      userId: req.user?.sub,
    });

    // Return success anyway - don't let logout fail
    return sendSuccess(res, {
      success: true,
      message: 'Logged out successfully',
    });
  }
});

module.exports = router;
