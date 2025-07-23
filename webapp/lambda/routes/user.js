/**
 * User Management Routes
 * Provides /api/user/* endpoints that proxy to existing /api/settings/* functionality
 * Plus additional user-specific features like password management
 */

const express = require('express');
// AWS Amplify functions will be loaded conditionally to avoid import errors
let changePassword, getCurrentUser;
try {
  const amplifyAuth = require('@aws-amplify/auth');
  changePassword = amplifyAuth.changePassword;
  getCurrentUser = amplifyAuth.getCurrentUser;
} catch (error) {
  console.warn('⚠️ AWS Amplify Auth not available, using fallback implementations');
  changePassword = null;
  getCurrentUser = null;
}
const { authenticateToken } = require('../middleware/auth');

const router = express.Router();

// Apply authentication middleware to all user routes
router.use(authenticateToken);

// Import settings router to reuse handlers
const settingsRouter = require('./settings');

// Helper function to proxy request to settings endpoint
const proxyToSettings = (settingsPath) => {
  return (req, res, next) => {
    // Create a new request object with the settings path
    const settingsReq = {
      ...req,
      url: settingsPath,
      originalUrl: req.originalUrl.replace('/api/user', '/api/settings'),
      baseUrl: '/api/settings'
    };
    
    // Find the matching route handler from settings
    const layer = settingsRouter.stack.find(layer => {
      if (!layer.route) return false;
      const routePath = layer.route.path;
      const method = req.method.toLowerCase();
      return routePath === settingsPath && layer.route.methods[method];
    });
    
    if (layer && layer.route) {
      // Execute the settings route handler
      const handler = layer.route.stack[0].handle;
      handler(settingsReq, res, next);
    } else {
      res.status(404).json({
        success: false,
        error: `Handler not found for ${settingsPath}`
      });
    }
  };
};

// Two-Factor Authentication endpoints
router.post('/two-factor/enable', async (req, res) => {
  try {
    console.log('🔐 2FA Enable requested');
    
    // For now, return a placeholder response until we implement full 2FA
    res.json({
      success: false,
      error: 'Two-factor authentication setup is coming soon',
      message: 'This feature will be available in the next update',
      requiresSetup: true
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: 'Failed to enable 2FA',
      message: error.message
    });
  }
});

router.post('/two-factor/disable', async (req, res) => {
  try {
    console.log('🔐 2FA Disable requested');
    
    res.json({
      success: false,
      error: 'Two-factor authentication management is coming soon',
      message: 'This feature will be available in the next update'
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: 'Failed to disable 2FA',
      message: error.message
    });
  }
});

router.post('/two-factor/verify', async (req, res) => {
  try {
    console.log('🔐 2FA Verify requested');
    
    res.json({
      success: false,
      error: 'Two-factor authentication verification is coming soon',
      message: 'This feature will be available in the next update'
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: 'Failed to verify 2FA',
      message: error.message
    });
  }
});

router.get('/two-factor/status', async (req, res) => {
  try {
    console.log('🔐 2FA Status requested');
    
    res.json({
      success: true,
      data: {
        enabled: false,
        setupRequired: true,
        backupCodes: 0,
        lastUsed: null
      },
      message: 'Two-factor authentication is not yet configured'
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: 'Failed to get 2FA status',
      message: error.message
    });
  }
});

// Recovery codes - proxy to settings
router.get('/recovery-codes', proxyToSettings('/recovery-codes'));

// Session management - proxy to settings
router.post('/revoke-sessions', proxyToSettings('/revoke-sessions'));

// Profile management - proxy to settings
router.get('/profile', proxyToSettings('/profile'));
router.put('/profile', proxyToSettings('/profile'));

// Notifications - proxy to settings
router.get('/notifications', proxyToSettings('/notifications'));
router.put('/notifications', proxyToSettings('/notifications'));

// Theme - proxy to settings
router.get('/theme', proxyToSettings('/theme'));
router.put('/theme', proxyToSettings('/theme'));

// Account deletion - proxy to settings
router.delete('/delete-account', proxyToSettings('/delete-account'));

// Password Management - New functionality
router.post('/change-password', async (req, res) => {
  try {
    console.log('🔒 User requesting password change...');
    const { currentPassword, newPassword } = req.body;
    
    // Validate input
    if (!currentPassword || !newPassword) {
      return res.status(400).json({
        success: false,
        error: 'Current password and new password are required'
      });
    }
    
    if (newPassword.length < 8) {
      return res.status(400).json({
        success: false,
        error: 'New password must be at least 8 characters long'
      });
    }
    
    // Password strength validation
    const hasUpperCase = /[A-Z]/.test(newPassword);
    const hasLowerCase = /[a-z]/.test(newPassword);
    const hasNumbers = /\d/.test(newPassword);
    const hasSpecialChar = /[!@#$%^&*(),.?":{}|<>]/.test(newPassword);
    
    if (!hasUpperCase || !hasLowerCase || !hasNumbers || !hasSpecialChar) {
      return res.status(400).json({
        success: false,
        error: 'Password must contain at least one uppercase letter, one lowercase letter, one number, and one special character'
      });
    }
    
    const userId = req.user.sub;
    console.log('🔒 Changing password for user:', userId);
    
    try {
      // Check if AWS Amplify is available
      if (!changePassword) {
        return res.status(503).json({
          success: false,
          error: 'Password change service unavailable',
          message: 'AWS Amplify authentication service is not configured'
        });
      }
      
      // Use AWS Amplify to change password
      await changePassword({
        oldPassword: currentPassword,
        newPassword: newPassword
      });
      
      console.log('✅ Password changed successfully for user:', userId);
      
      res.json({
        success: true,
        message: 'Password changed successfully'
      });
      
    } catch (authError) {
      console.error('❌ AWS Cognito password change error:', authError);
      
      if (authError.name === 'NotAuthorizedException' || authError.message?.includes('Incorrect username or password')) {
        return res.status(401).json({
          success: false,
          error: 'Current password is incorrect'
        });
      }
      
      if (authError.name === 'InvalidPasswordException') {
        return res.status(400).json({
          success: false,
          error: 'New password does not meet security requirements'
        });
      }
      
      if (authError.name === 'LimitExceededException') {
        return res.status(429).json({
          success: false,
          error: 'Too many password change attempts. Please try again later.'
        });
      }
      
      // Generic auth error
      return res.status(400).json({
        success: false,
        error: authError.message || 'Password change failed'
      });
    }
    
  } catch (error) {
    console.error('❌ Unexpected error changing password:', error);
    res.status(500).json({
      success: false,
      error: 'An unexpected error occurred while changing password',
      message: error.message
    });
  }
});

// Password reset initiation (for forgot password flow)
router.post('/forgot-password', async (req, res) => {
  try {
    const { email } = req.body;
    
    if (!email) {
      return res.status(400).json({
        success: false,
        error: 'Email address is required'
      });
    }
    
    console.log('📧 Initiating password reset for:', email);
    
    // Import resetPassword from auth context (this should be in a service)
    const { resetPassword } = require('@aws-amplify/auth');
    
    await resetPassword({ username: email });
    
    res.json({
      success: true,
      message: 'Password reset instructions have been sent to your email address'
    });
    
  } catch (error) {
    console.error('❌ Error initiating password reset:', error);
    
    // Don't reveal whether the email exists or not for security
    res.json({
      success: true,
      message: 'If an account with that email address exists, password reset instructions have been sent'
    });
  }
});

// Get user session information
router.get('/sessions', async (req, res) => {
  try {
    console.log('🔍 Getting user session info...');
    const userId = req.user.sub;
    
    // Get current session information
    const currentUser = await getCurrentUser();
    
    const sessionInfo = {
      userId: userId,
      username: currentUser.username,
      email: req.user.email,
      lastLoginTime: req.user.auth_time ? new Date(req.user.auth_time * 1000) : null,
      tokenIssuedAt: req.user.iat ? new Date(req.user.iat * 1000) : null,
      tokenExpiresAt: req.user.exp ? new Date(req.user.exp * 1000) : null,
      currentSession: true
    };
    
    res.json({
      success: true,
      sessions: [sessionInfo],
      activeSessionCount: 1
    });
    
  } catch (error) {
    console.error('❌ Error getting session info:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get session information',
      message: error.message
    });
  }
});

// Health check endpoint
router.get('/health', (req, res) => {
  res.json({
    success: true,
    service: 'user-management',
    timestamp: new Date().toISOString(),
    userId: req.user?.sub,
    endpoints: [
      'GET /api/user/profile',
      'PUT /api/user/profile', 
      'POST /api/user/two-factor/enable',
      'POST /api/user/two-factor/disable',
      'POST /api/user/two-factor/verify',
      'GET /api/user/two-factor/status',
      'GET /api/user/recovery-codes',
      'POST /api/user/change-password',
      'POST /api/user/forgot-password',
      'GET /api/user/sessions',
      'POST /api/user/revoke-sessions',
      'GET /api/user/notifications',
      'PUT /api/user/notifications',
      'GET /api/user/theme',
      'PUT /api/user/theme',
      'DELETE /api/user/delete-account'
    ]
  });
});

// Include User Profile management routes
const userProfileRouter = require('./user-profile');
router.use('/', userProfileRouter);

module.exports = router;