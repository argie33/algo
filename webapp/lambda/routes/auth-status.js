/**
 * Authentication Status and Management Routes
 * Provides authentication status, token generation, and debugging
 */

const express = require('express');
const router = express.Router();
const { getAuthStatus, generateTestToken, authenticateToken } = require('../middleware/auth');
const { success, error } = require('../utils/responseFormatter');

/**
 * GET /api/auth-status/status
 * Get current authentication system status
 */
router.get('/status', getAuthStatus);

/**
 * GET /api/auth-status/generate-dev-token
 * Generate a development token for testing (development mode only)
 */
router.get('/generate-dev-token', async (req, res) => {
  try {
    const isDevelopment = process.env.NODE_ENV === 'development' || !process.env.NODE_ENV;
    
    if (!isDevelopment) {
      return res.status(403).json({
        success: false,
        error: 'Development token generation not allowed in production',
        message: 'This endpoint is only available in development mode'
      });
    }

    const userId = req.query.userId || 'dev-user-' + Date.now();
    const email = req.query.email || 'dev@example.com';
    
    const token = generateTestToken(userId, email);
    
    res.json({
      success: true,
      message: 'Development token generated successfully',
      token: token,
      usage: {
        header: `Authorization: Bearer ${token}`,
        curlExample: `curl -H "Authorization: Bearer ${token}" http://localhost:3000/api/health`,
        userId: userId,
        email: email,
        expiresIn: '24 hours'
      },
      warning: 'This token is for development use only and should never be used in production'
    });
    
  } catch (err) {
    console.error('Failed to generate development token:', err);
    res.status(500).json({
      success: false,
      error: 'Failed to generate development token',
      message: err.message
    });
  }
});

/**
 * GET /api/auth-status/validate-token
 * Validate the current token and return user information
 */
router.get('/validate-token', authenticateToken, async (req, res) => {
  try {
    const authHeader = req.headers['authorization'];
    const token = authHeader && authHeader.split(' ')[1];
    
    if (!token) {
      return res.status(401).json({
        success: false,
        error: 'No token provided',
        message: 'Authorization header with Bearer token is required'
      });
    }

    // The token validation will be handled by the auth middleware
    // If we get here, the token is valid
    res.json({
      success: true,
      message: 'Token is valid',
      user: req.user ? {
        id: req.user.sub,
        email: req.user.email,
        username: req.user.username,
        role: req.user.role,
        groups: req.user.groups,
        authMethod: req.user.authMethod,
        isDevelopment: req.user.isDevelopment,
        authenticatedAt: req.user.authenticatedAt
      } : null,
      tokenInfo: {
        issuedAt: req.user?.tokenIssuedAt,
        expiresAt: req.user?.tokenExpiresAt,
        authMethod: req.user?.authMethod
      }
    });
    
  } catch (err) {
    console.error('Token validation error:', err);
    res.status(401).json({
      success: false,
      error: 'Token validation failed',
      message: err.message
    });
  }
});

/**
 * GET /api/auth-status/user-info
 * Get current authenticated user information
 */
router.get('/user-info', authenticateToken, async (req, res) => {
  try {
    if (!req.user) {
      return res.status(401).json({
        success: false,
        error: 'Not authenticated',
        message: 'User is not authenticated'
      });
    }

    res.json({
      success: true,
      user: {
        id: req.user.sub,
        email: req.user.email,
        username: req.user.username,
        role: req.user.role,
        groups: req.user.groups,
        profile: {
          givenName: req.user.givenName,
          familyName: req.user.familyName,
          emailVerified: req.user.emailVerified,
          phoneNumber: req.user.phoneNumber,
          phoneNumberVerified: req.user.phoneNumberVerified
        },
        customAttributes: {
          organization: req.user.organization,
          jobTitle: req.user.jobTitle,
          riskTolerance: req.user.riskTolerance,
          investmentExperience: req.user.investmentExperience,
          accreditedInvestor: req.user.accreditedInvestor
        },
        session: {
          authenticatedAt: req.user.authenticatedAt,
          authMethod: req.user.authMethod,
          isDevelopment: req.user.isDevelopment,
          clientIp: req.user.clientIp,
          requestId: req.user.requestId
        }
      }
    });
    
  } catch (err) {
    console.error('User info error:', err);
    res.status(500).json({
      success: false,
      error: 'Failed to get user information',
      message: err.message
    });
  }
});

/**
 * GET /api/auth-status/test-endpoints
 * Test different authentication scenarios
 */
router.get('/test-endpoints', async (req, res) => {
  try {
    const isDevelopment = process.env.NODE_ENV === 'development' || !process.env.NODE_ENV;
    
    if (!isDevelopment) {
      return res.status(403).json({
        success: false,
        error: 'Test endpoints not available in production'
      });
    }

    const baseUrl = req.protocol + '://' + req.get('host');
    const testToken = generateTestToken('test-user', 'test@example.com');
    
    res.json({
      success: true,
      message: 'Authentication test endpoints',
      endpoints: {
        'auth-status': {
          url: `${baseUrl}/api/auth-status/status`,
          method: 'GET',
          description: 'Get authentication system status',
          requiresAuth: false
        },
        'generate-token': {
          url: `${baseUrl}/api/auth-status/generate-dev-token`,
          method: 'GET',
          description: 'Generate development token',
          requiresAuth: false
        },
        'validate-token': {
          url: `${baseUrl}/api/auth-status/validate-token`,
          method: 'GET',
          description: 'Validate provided token',
          requiresAuth: true,
          header: `Authorization: Bearer ${testToken}`
        },
        'user-info': {
          url: `${baseUrl}/api/auth-status/user-info`,
          method: 'GET',
          description: 'Get authenticated user information',
          requiresAuth: true,
          header: `Authorization: Bearer ${testToken}`
        },
        'health-check': {
          url: `${baseUrl}/api/health/api-services`,
          method: 'GET',
          description: 'Test API services with authentication',
          requiresAuth: false
        }
      },
      sampleToken: testToken,
      curlExamples: {
        'test-without-auth': `curl "${baseUrl}/api/auth-status/status"`,
        'test-with-auth': `curl -H "Authorization: Bearer ${testToken}" "${baseUrl}/api/auth-status/user-info"`,
        'test-api-services': `curl -H "Authorization: Bearer ${testToken}" "${baseUrl}/api/health/api-services"`
      }
    });
    
  } catch (err) {
    console.error('Test endpoints error:', err);
    res.status(500).json({
      success: false,
      error: 'Failed to generate test endpoints',
      message: err.message
    });
  }
});

module.exports = router;