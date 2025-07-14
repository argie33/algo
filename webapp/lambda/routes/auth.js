const express = require('express');
const { CognitoIdentityProviderClient, InitiateAuthCommand, RespondToAuthChallengeCommand, SignUpCommand, ConfirmSignUpCommand, ForgotPasswordCommand, ConfirmForgotPasswordCommand } = require('@aws-sdk/client-cognito-identity-provider');
const { authenticateToken } = require('../middleware/auth');
const { 
  createValidationMiddleware, 
  rateLimitConfigs, 
  sqlInjectionPrevention, 
  xssPrevention,
  sanitizers,
  validationSchemas
} = require('../middleware/validation');
const validator = require('validator');

const router = express.Router();

// Initialize Cognito client
const cognitoClient = new CognitoIdentityProviderClient({
  region: process.env.AWS_REGION || process.env.WEBAPP_AWS_REGION || 'us-east-1'
});

// Authentication-specific validation schemas
const authValidationSchemas = {
  login: {
    username: {
      required: true,
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 100, escapeHTML: true }),
      validator: (value) => {
        // Allow email format or username format
        return validator.isEmail(value) || /^[a-zA-Z0-9_.-]{3,50}$/.test(value);
      },
      errorMessage: 'Username must be a valid email or 3-50 character alphanumeric username'
    },
    password: {
      required: true,
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 256 }),
      validator: (value) => value.length >= 8 && value.length <= 256,
      errorMessage: 'Password must be between 8 and 256 characters'
    }
  },

  signup: {
    username: {
      required: true,
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 50, escapeHTML: true }),
      validator: (value) => /^[a-zA-Z0-9_.-]{3,50}$/.test(value),
      errorMessage: 'Username must be 3-50 characters, alphanumeric with underscore, dot, or dash'
    },
    email: {
      required: true,
      type: 'string',
      sanitizer: sanitizers.email,
      validator: validator.isEmail,
      errorMessage: 'Invalid email format'
    },
    password: {
      required: true,
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 256 }),
      validator: (value) => {
        // Strong password requirements
        return value.length >= 8 && 
               /[A-Z]/.test(value) && 
               /[a-z]/.test(value) && 
               /[0-9]/.test(value) && 
               /[^A-Za-z0-9]/.test(value);
      },
      errorMessage: 'Password must be at least 8 characters with uppercase, lowercase, number, and special character'
    },
    phone: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 20 }),
      validator: (value) => !value || validator.isMobilePhone(value, 'any'),
      errorMessage: 'Invalid phone number format'
    }
  },

  challenge: {
    challengeName: {
      required: true,
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 50, alphaNumOnly: false }),
      validator: (value) => ['SMS_MFA', 'SOFTWARE_TOKEN_MFA', 'NEW_PASSWORD_REQUIRED', 'MFA_SETUP'].includes(value),
      errorMessage: 'Invalid challenge name'
    },
    session: {
      required: true,
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 2048 }),
      validator: (value) => value.length > 10,
      errorMessage: 'Invalid session token'
    }
  },

  confirmSignup: {
    username: {
      required: true,
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 100, escapeHTML: true }),
      validator: (value) => validator.isEmail(value) || /^[a-zA-Z0-9_.-]{3,50}$/.test(value),
      errorMessage: 'Username must be a valid email or alphanumeric username'
    },
    confirmationCode: {
      required: true,
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { alphaNumOnly: true, maxLength: 10 }),
      validator: (value) => /^[0-9]{6}$/.test(value),
      errorMessage: 'Confirmation code must be 6 digits'
    }
  },

  forgotPassword: {
    username: {
      required: true,
      type: 'string', 
      sanitizer: (value) => sanitizers.string(value, { maxLength: 100, escapeHTML: true }),
      validator: (value) => validator.isEmail(value) || /^[a-zA-Z0-9_.-]{3,50}$/.test(value),
      errorMessage: 'Username must be a valid email or alphanumeric username'
    }
  },

  confirmForgotPassword: {
    username: {
      required: true,
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 100, escapeHTML: true }),
      validator: (value) => validator.isEmail(value) || /^[a-zA-Z0-9_.-]{3,50}$/.test(value),
      errorMessage: 'Username must be a valid email or alphanumeric username'
    },
    confirmationCode: {
      required: true,
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { alphaNumOnly: true, maxLength: 10 }),
      validator: (value) => /^[0-9]{6}$/.test(value),
      errorMessage: 'Confirmation code must be 6 digits'
    },
    newPassword: {
      required: true,
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 256 }),
      validator: (value) => {
        return value.length >= 8 && 
               /[A-Z]/.test(value) && 
               /[a-z]/.test(value) && 
               /[0-9]/.test(value) && 
               /[^A-Za-z0-9]/.test(value);
      },
      errorMessage: 'Password must be at least 8 characters with uppercase, lowercase, number, and special character'
    }
  }
};

// Apply security middleware to all auth routes
router.use(sqlInjectionPrevention);
router.use(xssPrevention);
router.use(rateLimitConfigs.auth);

// User login
router.post('/login', createValidationMiddleware(authValidationSchemas.login), async (req, res) => {
  try {
    const { username, password } = req.validated;

    const command = new InitiateAuthCommand({
      AuthFlow: 'USER_PASSWORD_AUTH',
      ClientId: process.env.COGNITO_CLIENT_ID,
      AuthParameters: {
        USERNAME: username,
        PASSWORD: password
      }
    });

    const response = await cognitoClient.send(command);

    if (response.ChallengeName) {
      // Handle auth challenges (MFA, password change, etc.)
      return res.json({
        challenge: response.ChallengeName,
        challengeParameters: response.ChallengeParameters,
        session: response.Session
      });
    }

    // Successful authentication
    return res.json({
      accessToken: response.AuthenticationResult.AccessToken,
      idToken: response.AuthenticationResult.IdToken,
      refreshToken: response.AuthenticationResult.RefreshToken,
      expiresIn: response.AuthenticationResult.ExpiresIn,
      tokenType: response.AuthenticationResult.TokenType
    });

  } catch (error) {
    console.error('Login error:', error);
    
    if (error.name === 'NotAuthorizedException') {
      return res.status(401).json({
        error: 'Invalid credentials',
        message: 'The username or password is incorrect'
      });
    }
    
    if (error.name === 'UserNotConfirmedException') {
      return res.status(401).json({
        error: 'Account not confirmed',
        message: 'Please confirm your account before signing in'
      });
    }

    return res.status(500).json({
      error: 'Authentication failed',
      message: 'An error occurred during authentication'
    });
  }
});

// Handle auth challenges (MFA, password reset, etc.)
router.post('/challenge', createValidationMiddleware(authValidationSchemas.challenge), async (req, res) => {
  try {
    const { challengeName, session } = req.validated;
    const { challengeResponses } = req.body;

    const command = new RespondToAuthChallengeCommand({
      ClientId: process.env.COGNITO_CLIENT_ID,
      ChallengeName: challengeName,
      ChallengeResponses: challengeResponses,
      Session: session
    });

    const response = await cognitoClient.send(command);

    if (response.ChallengeName) {
      // Another challenge is required
      return res.json({
        challenge: response.ChallengeName,
        challengeParameters: response.ChallengeParameters,
        session: response.Session
      });
    }

    // Authentication completed
    return res.json({
      accessToken: response.AuthenticationResult.AccessToken,
      idToken: response.AuthenticationResult.IdToken,
      refreshToken: response.AuthenticationResult.RefreshToken,
      expiresIn: response.AuthenticationResult.ExpiresIn,
      tokenType: response.AuthenticationResult.TokenType
    });

  } catch (error) {
    console.error('Challenge response error:', error);
    return res.status(400).json({
      error: 'Challenge failed',
      message: 'Failed to respond to authentication challenge'
    });
  }
});

// User registration  
router.post('/register', createValidationMiddleware(authValidationSchemas.signup), async (req, res) => {
  try {
    const { username, password, email } = req.validated;
    const { firstName, lastName } = req.body;

    const command = new SignUpCommand({
      ClientId: process.env.COGNITO_CLIENT_ID,
      Username: username,
      Password: password,
      UserAttributes: [
        { Name: 'email', Value: email },
        ...(firstName ? [{ Name: 'given_name', Value: firstName }] : []),
        ...(lastName ? [{ Name: 'family_name', Value: lastName }] : [])
      ]
    });

    const response = await cognitoClient.send(command);

    return res.json({
      message: 'User registered successfully',
      userSub: response.UserSub,
      codeDeliveryDetails: response.CodeDeliveryDetails
    });

  } catch (error) {
    console.error('Registration error:', error);
    
    if (error.name === 'UsernameExistsException') {
      return res.status(400).json({
        error: 'Username exists',
        message: 'A user with this username already exists'
      });
    }

    if (error.name === 'InvalidParameterException') {
      return res.status(400).json({
        error: 'Invalid parameters',
        message: error.message
      });
    }

    return res.status(500).json({
      error: 'Registration failed',
      message: 'An error occurred during registration'
    });
  }
});

// Confirm user registration
router.post('/confirm', createValidationMiddleware(authValidationSchemas.confirmSignup), async (req, res) => {
  try {
    const { username, confirmationCode } = req.validated;

    const command = new ConfirmSignUpCommand({
      ClientId: process.env.COGNITO_CLIENT_ID,
      Username: username,
      ConfirmationCode: confirmationCode
    });

    await cognitoClient.send(command);

    return res.json({
      message: 'Account confirmed successfully'
    });

  } catch (error) {
    console.error('Confirmation error:', error);
    
    if (error.name === 'CodeMismatchException') {
      return res.status(400).json({
        error: 'Invalid code',
        message: 'The confirmation code is incorrect'
      });
    }

    return res.status(400).json({
      error: 'Confirmation failed',
      message: 'Failed to confirm account'
    });
  }
});

// Forgot password
router.post('/forgot-password', createValidationMiddleware(authValidationSchemas.forgotPassword), async (req, res) => {
  try {
    const { username } = req.validated;

    const command = new ForgotPasswordCommand({
      ClientId: process.env.COGNITO_CLIENT_ID,
      Username: username
    });

    const response = await cognitoClient.send(command);

    return res.json({
      message: 'Password reset code sent',
      codeDeliveryDetails: response.CodeDeliveryDetails
    });

  } catch (error) {
    console.error('Forgot password error:', error);
    return res.status(400).json({
      error: 'Password reset failed',
      message: 'Failed to initiate password reset'
    });
  }
});

// Confirm forgot password
router.post('/reset-password', createValidationMiddleware(authValidationSchemas.confirmForgotPassword), async (req, res) => {
  try {
    const { username, confirmationCode, newPassword } = req.validated;

    const command = new ConfirmForgotPasswordCommand({
      ClientId: process.env.COGNITO_CLIENT_ID,
      Username: username,
      ConfirmationCode: confirmationCode,
      Password: newPassword
    });

    await cognitoClient.send(command);

    return res.json({
      message: 'Password reset successfully'
    });

  } catch (error) {
    console.error('Reset password error:', error);
    return res.status(400).json({
      error: 'Password reset failed',
      message: 'Failed to reset password'
    });
  }
});

// Get current user info (protected route)
router.get('/me', authenticateToken, (req, res) => {
  res.json({
    user: req.user
  });
});

// Health check for auth service
router.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    service: 'Authentication Service',
    timestamp: new Date().toISOString(),
    cognito: {
      userPoolId: process.env.COGNITO_USER_POOL_ID ? 'configured' : 'not_configured',
      clientId: process.env.COGNITO_CLIENT_ID ? 'configured' : 'not_configured',
      region: process.env.AWS_REGION || process.env.WEBAPP_AWS_REGION || 'us-east-1'
    }
  });
});

module.exports = router;