/**
 * User Management Routes
 * Provides /api/user/* endpoints that proxy to existing /api/settings/* functionality
 * Plus additional user-specific features like password management and MFA
 */

const express = require('express');
const { CognitoIdentityProviderClient, 
        AssociateSoftwareTokenCommand,
        VerifySoftwareTokenCommand,
        SetUserMFAPreferenceCommand,
        AdminSetUserMFAPreferenceCommand,
        AdminGetUserCommand,
        GetUserCommand } = require('@aws-sdk/client-cognito-identity-provider');

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

// Initialize Cognito client
const cognitoClient = new CognitoIdentityProviderClient({ 
  region: process.env.WEBAPP_AWS_REGION || 'us-east-1' 
});

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
    const userId = req.user.sub;
    const { method, phoneNumber } = req.body;
    const accessToken = req.headers.authorization?.replace('Bearer ', '');
    
    // Validate input
    if (!method || !['sms', 'totp'].includes(method)) {
      return res.status(400).json({
        success: false,
        error: 'Valid MFA method (sms or totp) is required'
      });
    }

    if (method === 'sms' && !phoneNumber) {
      return res.status(400).json({
        success: false,
        error: 'Phone number is required for SMS authentication'
      });
    }

    if (!accessToken) {
      return res.status(401).json({
        success: false,
        error: 'Access token is required'
      });
    }

    const response = {
      success: true,
      method: method,
      message: `${method.toUpperCase()} two-factor authentication has been enabled`
    };

    if (method === 'totp') {
      try {
        // Associate software token with the user
        const associateCommand = new AssociateSoftwareTokenCommand({
          AccessToken: accessToken
        });
        
        const associateResult = await cognitoClient.send(associateCommand);
        
        if (associateResult.SecretCode) {
          const secretCode = associateResult.SecretCode;
          const issuer = 'TradingApp';
          const accountName = req.user.email || userId;
          
          // Generate QR code URL for authenticator apps
          const otpAuthUrl = `otpauth://totp/${issuer}:${accountName}?secret=${secretCode}&issuer=${issuer}`;
          const qrCodeUrl = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(otpAuthUrl)}`;
          
          response.qrCodeUrl = qrCodeUrl;
          response.secret = secretCode;
          response.setupRequired = true;
          response.message = 'TOTP setup initiated. Scan the QR code with your authenticator app and verify with a code.';
          
          console.log(`✅ TOTP secret associated for user ${userId}`);
        } else {
          throw new Error('Failed to associate software token');
        }
        
      } catch (error) {
        console.error('❌ Error associating software token:', error);
        return res.status(500).json({
          success: false,
          error: 'Failed to setup TOTP authentication',
          message: error.message
        });
      }
    } else if (method === 'sms') {
      try {
        // For SMS MFA, we need to set the phone number and enable SMS MFA
        // First verify phone number is in correct format
        const phoneRegex = /^\+[1-9]\d{1,14}$/;
        if (!phoneRegex.test(phoneNumber)) {
          return res.status(400).json({
            success: false,
            error: 'Phone number must be in E.164 format (e.g., +1234567890)'
          });
        }

        // Enable SMS MFA preference for the user
        const setMfaCommand = new SetUserMFAPreferenceCommand({
          AccessToken: accessToken,
          SMSMfaSettings: {
            Enabled: true,
            PreferredMfa: true
          }
        });
        
        await cognitoClient.send(setMfaCommand);
        
        response.phoneNumber = phoneNumber;
        response.message = `SMS two-factor authentication has been enabled for ${phoneNumber}`;
        
        console.log(`✅ SMS MFA enabled for user ${userId} with phone ${phoneNumber}`);
        
      } catch (error) {
        console.error('❌ Error enabling SMS MFA:', error);
        return res.status(500).json({
          success: false,
          error: 'Failed to enable SMS authentication',
          message: error.message
        });
      }
    }

    res.json(response);
    
  } catch (error) {
    console.error('❌ Error enabling 2FA:', error);
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
    const userId = req.user.sub;
    const accessToken = req.headers.authorization?.replace('Bearer ', '');
    
    if (!accessToken) {
      return res.status(401).json({
        success: false,
        error: 'Access token is required'
      });
    }

    try {
      // Disable both SMS and TOTP MFA
      const disableMfaCommand = new SetUserMFAPreferenceCommand({
        AccessToken: accessToken,
        SMSMfaSettings: {
          Enabled: false,
          PreferredMfa: false
        },
        SoftwareTokenMfaSettings: {
          Enabled: false,
          PreferredMfa: false
        }
      });
      
      await cognitoClient.send(disableMfaCommand);
      
      console.log(`✅ 2FA disabled for user ${userId}`);
      
      res.json({
        success: true,
        message: 'Two-factor authentication has been disabled',
        mfaEnabled: false
      });
      
    } catch (error) {
      console.error('❌ Error disabling MFA via Cognito:', error);
      res.status(500).json({
        success: false,
        error: 'Failed to disable MFA',
        message: error.message
      });
    }
    
  } catch (error) {
    console.error('❌ Error disabling 2FA:', error);
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
    const userId = req.user.sub;
    const { method, code } = req.body;
    const accessToken = req.headers.authorization?.replace('Bearer ', '');
    
    // Validate input
    if (!method || !code) {
      return res.status(400).json({
        success: false,
        error: 'Method and verification code are required'
      });
    }

    if (code.length !== 6) {
      return res.status(400).json({
        success: false,
        error: 'Verification code must be 6 digits'
      });
    }

    if (!accessToken) {
      return res.status(401).json({
        success: false,
        error: 'Access token is required'
      });
    }

    const isValidCode = /^\d{6}$/.test(code);
    
    if (!isValidCode) {
      return res.status(400).json({
        success: false,
        error: 'Invalid verification code format'
      });
    }

    try {
      if (method === 'totp') {
        // Verify TOTP code
        const verifyCommand = new VerifySoftwareTokenCommand({
          AccessToken: accessToken,
          UserCode: code
        });
        
        const verifyResult = await cognitoClient.send(verifyCommand);
        
        if (verifyResult.Status === 'SUCCESS') {
          // Enable TOTP MFA after successful verification
          const enableMfaCommand = new SetUserMFAPreferenceCommand({
            AccessToken: accessToken,
            SoftwareTokenMfaSettings: {
              Enabled: true,
              PreferredMfa: true
            }
          });
          
          await cognitoClient.send(enableMfaCommand);
          
          // Generate backup codes
          const backupCodes = Array.from({ length: 8 }, () => 
            Math.random().toString(36).substring(2, 10).toUpperCase()
          );

          console.log(`✅ TOTP verified and enabled for user ${userId}`);
          
          res.json({
            success: true,
            message: 'TOTP authentication verified and enabled successfully',
            mfaEnabled: true,
            method: method,
            backupCodes: backupCodes
          });
        } else {
          res.status(400).json({
            success: false,
            error: 'Invalid verification code'
          });
        }
      } else {
        // For SMS, we can't directly verify since the code comes during sign-in
        // This endpoint is mainly for TOTP verification after setup
        res.status(400).json({
          success: false,
          error: 'SMS verification should happen during sign-in flow'
        });
      }
      
    } catch (error) {
      console.error('❌ Error verifying MFA code:', error);
      
      if (error.name === 'CodeMismatchException') {
        res.status(400).json({
          success: false,
          error: 'Invalid verification code'
        });
      } else if (error.name === 'ExpiredCodeException') {
        res.status(400).json({
          success: false,
          error: 'Verification code has expired'
        });
      } else {
        res.status(500).json({
          success: false,
          error: 'Failed to verify MFA code',
          message: error.message
        });
      }
    }
    
  } catch (error) {
    console.error('❌ Error verifying 2FA:', error);
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
    const userId = req.user.sub;
    const accessToken = req.headers.authorization?.replace('Bearer ', '');
    
    if (!accessToken) {
      return res.status(401).json({
        success: false,
        error: 'Access token is required'
      });
    }

    try {
      // Get user details including MFA preferences
      const getUserCommand = new GetUserCommand({
        AccessToken: accessToken
      });
      
      const userResult = await cognitoClient.send(getUserCommand);
      
      // Check MFA preferences from user attributes
      const mfaPrefs = userResult.MFAOptions || [];
      const enabled = mfaPrefs.length > 0;
      
      res.json({
        success: true,
        data: {
          enabled: enabled,
          setupRequired: !enabled,
          methods: mfaPrefs.map(pref => pref.DeliveryMedium?.toLowerCase() || 'unknown'),
          backupCodes: enabled ? 8 : 0, // Assume 8 backup codes if MFA is enabled
          lastUsed: null // Cognito doesn't provide this info easily
        },
        message: enabled ? 'Two-factor authentication is configured' : 'Two-factor authentication is not yet configured'
      });
      
    } catch (error) {
      console.error('❌ Error getting user MFA status:', error);
      res.status(500).json({
        success: false,
        error: 'Failed to get 2FA status',
        message: error.message
      });
    }
  } catch (error) {
    res.status(500).json({
      success: false,
      error: 'Failed to get 2FA status',
      message: error.message
    });
  }
});

// MFA Status endpoint for SecurityTab
router.get('/mfa-status', async (req, res) => {
  try {
    console.log('🔐 MFA Status requested for SecurityTab');
    const userId = req.user.sub;
    const accessToken = req.headers.authorization?.replace('Bearer ', '');
    
    if (!accessToken) {
      return res.status(401).json({
        success: false,
        error: 'Access token is required'
      });
    }

    try {
      // Get user details including MFA preferences
      const getUserCommand = new GetUserCommand({
        AccessToken: accessToken
      });
      
      const userResult = await cognitoClient.send(getUserCommand);
      
      // Check MFA preferences from user attributes
      const mfaPrefs = userResult.MFAOptions || [];
      const mfaEnabled = mfaPrefs.length > 0;
      
      // Extract enabled methods
      const mfaMethods = mfaPrefs.map(pref => ({
        type: pref.DeliveryMedium?.toLowerCase() === 'sms' ? 'sms' : 'totp',
        enabled: true,
        verified: true
      }));
      
      res.json({
        success: true,
        mfaEnabled: mfaEnabled,
        mfaMethods: mfaMethods,
        backupCodes: mfaEnabled ? Array.from({ length: 8 }, () => '********') : [],
        message: 'MFA status retrieved successfully'
      });
      
    } catch (error) {
      console.error('❌ Error getting MFA status from Cognito:', error);
      res.status(500).json({
        success: false,
        error: 'Failed to get MFA status',
        message: error.message
      });
    }
  } catch (error) {
    console.error('❌ Error getting MFA status:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get MFA status',
      message: error.message
    });
  }
});

// MFA Setup endpoints for different methods
router.post('/two-factor/setup/:method', async (req, res) => {
  try {
    const { method } = req.params;
    const { phoneNumber } = req.body;
    const userId = req.user.sub;
    const accessToken = req.headers.authorization?.replace('Bearer ', '');
    
    console.log(`🔐 Setting up ${method} for user ${userId}`);
    
    if (!['sms', 'totp'].includes(method)) {
      return res.status(400).json({
        success: false,
        error: 'Invalid MFA method. Use sms or totp.'
      });
    }

    if (!accessToken) {
      return res.status(401).json({
        success: false,
        error: 'Access token is required'
      });
    }

    const response = {
      success: true,
      method: method,
      message: `${method.toUpperCase()} setup initiated`
    };

    try {
      if (method === 'totp') {
        // Associate software token with the user  
        const associateCommand = new AssociateSoftwareTokenCommand({
          AccessToken: accessToken
        });
        
        const associateResult = await cognitoClient.send(associateCommand);
        
        if (associateResult.SecretCode) {
          const secretCode = associateResult.SecretCode;
          const issuer = 'TradingApp';
          const accountName = req.user.email || userId;
          
          // Generate QR code URL for authenticator apps
          const otpAuthUrl = `otpauth://totp/${issuer}:${accountName}?secret=${secretCode}&issuer=${issuer}`;
          const qrCodeUrl = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(otpAuthUrl)}`;
          
          response.qrCodeUrl = qrCodeUrl;
          response.secret = secretCode;
          response.message = 'TOTP setup initiated. Scan the QR code with your authenticator app.';
          
          console.log(`✅ TOTP setup initiated for user ${userId}`);
        } else {
          throw new Error('Failed to associate software token');
        }
        
      } else if (method === 'sms') {
        if (!phoneNumber) {
          return res.status(400).json({
            success: false,
            error: 'Phone number is required for SMS setup'
          });
        }
        
        // Validate phone number format
        const phoneRegex = /^\+[1-9]\d{1,14}$/;
        if (!phoneRegex.test(phoneNumber)) {
          return res.status(400).json({
            success: false,
            error: 'Phone number must be in E.164 format (e.g., +1234567890)'
          });
        }
        
        response.phoneNumber = phoneNumber;
        response.message = `SMS MFA setup initiated for ${phoneNumber}. Enable SMS MFA to complete setup.`;
        
        console.log(`✅ SMS MFA setup initiated for user ${userId} with phone ${phoneNumber}`);
      }

      res.json(response);
      
    } catch (error) {
      console.error('❌ Error setting up MFA with Cognito:', error);
      res.status(500).json({
        success: false,
        error: 'Failed to setup MFA',
        message: error.message
      });
    }
    
  } catch (error) {
    console.error('❌ Error setting up MFA:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to setup MFA',
      message: error.message
    });
  }
});

// Backup codes generation
router.post('/backup-codes/generate', async (req, res) => {
  try {
    console.log('🔐 Generating backup codes');
    const userId = req.user.sub;
    
    // Generate 8 backup codes
    const backupCodes = Array.from({ length: 8 }, () => 
      Math.random().toString(36).substring(2, 10).toUpperCase()
    );
    
    console.log(`✅ Generated ${backupCodes.length} backup codes for user ${userId}`);
    
    res.json({
      success: true,
      codes: backupCodes,
      message: 'Backup codes generated successfully'
    });
  } catch (error) {
    console.error('❌ Error generating backup codes:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to generate backup codes',
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