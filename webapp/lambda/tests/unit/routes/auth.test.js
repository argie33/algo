/**
 * Unit Tests for Authentication Routes
 * Tests user login, registration, and password management
 */

const request = require('supertest');
const express = require('express');

// Mock AWS Cognito SDK
const mockCognitoClient = {
  send: jest.fn()
};

jest.mock('@aws-sdk/client-cognito-identity-provider', () => ({
  CognitoIdentityProviderClient: jest.fn(() => mockCognitoClient),
  InitiateAuthCommand: jest.fn(),
  RespondToAuthChallengeCommand: jest.fn(),
  SignUpCommand: jest.fn(),
  ConfirmSignUpCommand: jest.fn(),
  ForgotPasswordCommand: jest.fn(),
  ConfirmForgotPasswordCommand: jest.fn()
}));

// Mock authentication middleware
jest.mock('../../../middleware/auth', () => ({
  authenticateToken: (req, res, next) => {
    req.user = { sub: 'test-user-id', email: 'test@example.com' };
    next();
  }
}));

const authRoutes = require('../../../routes/auth');
const app = express();
app.use(express.json());
app.use('/api/auth', authRoutes);

const {
  InitiateAuthCommand,
  SignUpCommand,
  ConfirmSignUpCommand,
  ForgotPasswordCommand,
  ConfirmForgotPasswordCommand,
  RespondToAuthChallengeCommand
} = require('@aws-sdk/client-cognito-identity-provider');

describe('Authentication Routes', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    process.env.COGNITO_CLIENT_ID = 'test-client-id';
    process.env.COGNITO_USER_POOL_ID = 'test-user-pool-id';
  });

  afterEach(() => {
    delete process.env.COGNITO_CLIENT_ID;
    delete process.env.COGNITO_USER_POOL_ID;
  });

  describe('POST /api/auth/login', () => {
    it('should successfully authenticate user with valid credentials', async () => {
      const mockAuthResponse = {
        AuthenticationResult: {
          AccessToken: 'mock-access-token',
          RefreshToken: 'mock-refresh-token',
          IdToken: 'mock-id-token'
        }
      };

      mockCognitoClient.send.mockResolvedValue(mockAuthResponse);

      const response = await request(app)
        .post('/api/auth/login')
        .send({
          username: 'testuser@example.com',
          password: 'TestPassword123!'
        })
        .expect(200);

      expect(response.body).toHaveProperty('tokens');
      expect(response.body.tokens).toHaveProperty('accessToken', 'mock-access-token');
      expect(response.body.tokens).toHaveProperty('refreshToken', 'mock-refresh-token');
      expect(response.body.tokens).toHaveProperty('idToken', 'mock-id-token');
      
      expect(InitiateAuthCommand).toHaveBeenCalledWith({
        AuthFlow: 'USER_PASSWORD_AUTH',
        ClientId: 'test-client-id',
        AuthParameters: {
          USERNAME: 'testuser@example.com',
          PASSWORD: 'TestPassword123!'
        }
      });
    });

    it('should handle MFA challenge', async () => {
      const mockChallengeResponse = {
        ChallengeName: 'SMS_MFA',
        ChallengeParameters: {
          CODE_DELIVERY_DELIVERY_MEDIUM: 'SMS',
          CODE_DELIVERY_DESTINATION: '+***9999'
        },
        Session: 'mock-session-id'
      };

      mockCognitoClient.send.mockResolvedValue(mockChallengeResponse);

      const response = await request(app)
        .post('/api/auth/login')
        .send({
          username: 'testuser@example.com',
          password: 'TestPassword123!'
        })
        .expect(200);

      expect(response.body).toHaveProperty('challenge', 'SMS_MFA');
      expect(response.body).toHaveProperty('challengeParameters');
      expect(response.body).toHaveProperty('session', 'mock-session-id');
    });

    it('should reject login with missing credentials', async () => {
      const response = await request(app)
        .post('/api/auth/login')
        .send({})
        .expect(400);

      expect(response.body).toHaveProperty('error', 'Missing credentials');
      expect(response.body).toHaveProperty('message', 'Username and password are required');
      expect(mockCognitoClient.send).not.toHaveBeenCalled();
    });

    it('should handle invalid credentials', async () => {
      const authError = new Error('Incorrect username or password.');
      authError.name = 'NotAuthorizedException';
      mockCognitoClient.send.mockRejectedValue(authError);

      const response = await request(app)
        .post('/api/auth/login')
        .send({
          username: 'testuser@example.com',
          password: 'wrongpassword'
        })
        .expect(401);

      expect(response.body).toHaveProperty('error', 'Invalid credentials');
    });

    it('should handle user not found', async () => {
      const userNotFoundError = new Error('User does not exist.');
      userNotFoundError.name = 'UserNotFoundException';
      mockCognitoClient.send.mockRejectedValue(userNotFoundError);

      const response = await request(app)
        .post('/api/auth/login')
        .send({
          username: 'nonexistent@example.com',
          password: 'TestPassword123!'
        })
        .expect(404);

      expect(response.body).toHaveProperty('error', 'User not found');
    });

    it('should handle account not confirmed', async () => {
      const notConfirmedError = new Error('User is not confirmed.');
      notConfirmedError.name = 'UserNotConfirmedException';
      mockCognitoClient.send.mockRejectedValue(notConfirmedError);

      const response = await request(app)
        .post('/api/auth/login')
        .send({
          username: 'unconfirmed@example.com',
          password: 'TestPassword123!'
        })
        .expect(403);

      expect(response.body).toHaveProperty('error', 'Account not confirmed');
    });

    it('should handle temporary password challenge', async () => {
      const tempPasswordResponse = {
        ChallengeName: 'NEW_PASSWORD_REQUIRED',
        ChallengeParameters: {
          USER_ATTRIBUTES: '{"email":"test@example.com"}',
          requiredAttributes: '[]'
        },
        Session: 'temp-session-id'
      };

      mockCognitoClient.send.mockResolvedValue(tempPasswordResponse);

      const response = await request(app)
        .post('/api/auth/login')
        .send({
          username: 'testuser@example.com',
          password: 'TempPassword123!'
        })
        .expect(200);

      expect(response.body).toHaveProperty('challenge', 'NEW_PASSWORD_REQUIRED');
      expect(response.body).toHaveProperty('session', 'temp-session-id');
    });
  });

  describe('POST /api/auth/register', () => {
    it('should successfully register new user', async () => {
      const mockSignUpResponse = {
        UserSub: 'user-123-456',
        CodeDeliveryDetails: {
          DeliveryMedium: 'EMAIL',
          Destination: 't***@example.com'
        }
      };

      mockCognitoClient.send.mockResolvedValue(mockSignUpResponse);

      const response = await request(app)
        .post('/api/auth/register')
        .send({
          username: 'newuser@example.com',
          password: 'NewPassword123!',
          email: 'newuser@example.com',
          firstName: 'New',
          lastName: 'User'
        })
        .expect(200);

      expect(response.body).toHaveProperty('userSub', 'user-123-456');
      expect(response.body).toHaveProperty('confirmationRequired', true);
      
      expect(SignUpCommand).toHaveBeenCalledWith(expect.objectContaining({
        ClientId: 'test-client-id',
        Username: 'newuser@example.com',
        Password: 'NewPassword123!'
      }));
    });

    it('should reject registration with missing required fields', async () => {
      const response = await request(app)
        .post('/api/auth/register')
        .send({
          username: 'incomplete@example.com'
        })
        .expect(400);

      expect(response.body).toHaveProperty('error', 'Missing required fields');
      expect(mockCognitoClient.send).not.toHaveBeenCalled();
    });

    it('should handle username already exists error', async () => {
      const usernameExistsError = new Error('An account with the given email already exists.');
      usernameExistsError.name = 'UsernameExistsException';
      mockCognitoClient.send.mockRejectedValue(usernameExistsError);

      const response = await request(app)
        .post('/api/auth/register')
        .send({
          username: 'existing@example.com',
          password: 'Password123!',
          email: 'existing@example.com',
          firstName: 'Test',
          lastName: 'User'
        })
        .expect(409);

      expect(response.body).toHaveProperty('error', 'Username already exists');
    });

    it('should handle invalid password format', async () => {
      const invalidPasswordError = new Error('Password does not conform to policy');
      invalidPasswordError.name = 'InvalidPasswordException';
      mockCognitoClient.send.mockRejectedValue(invalidPasswordError);

      const response = await request(app)
        .post('/api/auth/register')
        .send({
          username: 'newuser@example.com',
          password: 'weak',
          email: 'newuser@example.com',
          firstName: 'Test',
          lastName: 'User'
        })
        .expect(400);

      expect(response.body).toHaveProperty('error', 'Invalid password format');
    });
  });

  describe('POST /api/auth/confirm', () => {
    it('should successfully confirm user registration', async () => {
      mockCognitoClient.send.mockResolvedValue({});

      const response = await request(app)
        .post('/api/auth/confirm')
        .send({
          username: 'testuser@example.com',
          confirmationCode: '123456'
        })
        .expect(200);

      expect(response.body).toHaveProperty('message', 'Account confirmed successfully');
      
      expect(ConfirmSignUpCommand).toHaveBeenCalledWith({
        ClientId: 'test-client-id',
        Username: 'testuser@example.com',
        ConfirmationCode: '123456'
      });
    });

    it('should reject confirmation with missing parameters', async () => {
      const response = await request(app)
        .post('/api/auth/confirm')
        .send({
          username: 'testuser@example.com'
        })
        .expect(400);

      expect(response.body).toHaveProperty('error', 'Missing required parameters');
      expect(mockCognitoClient.send).not.toHaveBeenCalled();
    });

    it('should handle invalid confirmation code', async () => {
      const invalidCodeError = new Error('Invalid verification code provided');
      invalidCodeError.name = 'CodeMismatchException';
      mockCognitoClient.send.mockRejectedValue(invalidCodeError);

      const response = await request(app)
        .post('/api/auth/confirm')
        .send({
          username: 'testuser@example.com',
          confirmationCode: '000000'
        })
        .expect(400);

      expect(response.body).toHaveProperty('error', 'Invalid confirmation code');
    });

    it('should handle expired confirmation code', async () => {
      const expiredCodeError = new Error('Invalid code provided');
      expiredCodeError.name = 'ExpiredCodeException';
      mockCognitoClient.send.mockRejectedValue(expiredCodeError);

      const response = await request(app)
        .post('/api/auth/confirm')
        .send({
          username: 'testuser@example.com',
          confirmationCode: '123456'
        })
        .expect(400);

      expect(response.body).toHaveProperty('error', 'Confirmation code expired');
    });
  });

  describe('POST /api/auth/forgot-password', () => {
    it('should successfully initiate password reset', async () => {
      const mockForgotPasswordResponse = {
        CodeDeliveryDetails: {
          DeliveryMedium: 'EMAIL',
          Destination: 't***@example.com'
        }
      };

      mockCognitoClient.send.mockResolvedValue(mockForgotPasswordResponse);

      const response = await request(app)
        .post('/api/auth/forgot-password')
        .send({
          username: 'testuser@example.com'
        })
        .expect(200);

      expect(response.body).toHaveProperty('message', 'Password reset code sent');
      expect(response.body).toHaveProperty('codeDeliveryDetails');
      
      expect(ForgotPasswordCommand).toHaveBeenCalledWith({
        ClientId: 'test-client-id',
        Username: 'testuser@example.com'
      });
    });

    it('should reject request with missing username', async () => {
      const response = await request(app)
        .post('/api/auth/forgot-password')
        .send({})
        .expect(400);

      expect(response.body).toHaveProperty('error', 'Username is required');
      expect(mockCognitoClient.send).not.toHaveBeenCalled();
    });

    it('should handle user not found for password reset', async () => {
      const userNotFoundError = new Error('User does not exist');
      userNotFoundError.name = 'UserNotFoundException';
      mockCognitoClient.send.mockRejectedValue(userNotFoundError);

      const response = await request(app)
        .post('/api/auth/forgot-password')
        .send({
          username: 'nonexistent@example.com'
        })
        .expect(404);

      expect(response.body).toHaveProperty('error', 'User not found');
    });
  });

  describe('POST /api/auth/confirm-forgot-password', () => {
    it('should successfully reset password with valid code', async () => {
      mockCognitoClient.send.mockResolvedValue({});

      const response = await request(app)
        .post('/api/auth/confirm-forgot-password')
        .send({
          username: 'testuser@example.com',
          confirmationCode: '123456',
          newPassword: 'NewPassword123!'
        })
        .expect(200);

      expect(response.body).toHaveProperty('message', 'Password reset successfully');
      
      expect(ConfirmForgotPasswordCommand).toHaveBeenCalledWith({
        ClientId: 'test-client-id',
        Username: 'testuser@example.com',
        ConfirmationCode: '123456',
        Password: 'NewPassword123!'
      });
    });

    it('should reject with missing required parameters', async () => {
      const response = await request(app)
        .post('/api/auth/confirm-forgot-password')
        .send({
          username: 'testuser@example.com',
          confirmationCode: '123456'
        })
        .expect(400);

      expect(response.body).toHaveProperty('error', 'Missing required parameters');
      expect(mockCognitoClient.send).not.toHaveBeenCalled();
    });

    it('should handle invalid reset code', async () => {
      const invalidCodeError = new Error('Invalid verification code provided');
      invalidCodeError.name = 'CodeMismatchException';
      mockCognitoClient.send.mockRejectedValue(invalidCodeError);

      const response = await request(app)
        .post('/api/auth/confirm-forgot-password')
        .send({
          username: 'testuser@example.com',
          confirmationCode: '000000',
          newPassword: 'NewPassword123!'
        })
        .expect(400);

      expect(response.body).toHaveProperty('error', 'Invalid confirmation code');
    });
  });

  describe('POST /api/auth/respond-to-challenge', () => {
    it('should successfully respond to MFA challenge', async () => {
      const mockChallengeResponse = {
        AuthenticationResult: {
          AccessToken: 'mock-access-token',
          RefreshToken: 'mock-refresh-token',
          IdToken: 'mock-id-token'
        }
      };

      mockCognitoClient.send.mockResolvedValue(mockChallengeResponse);

      const response = await request(app)
        .post('/api/auth/respond-to-challenge')
        .send({
          challengeName: 'SMS_MFA',
          session: 'mock-session-id',
          challengeResponses: {
            SMS_MFA_CODE: '123456'
          }
        })
        .expect(200);

      expect(response.body).toHaveProperty('tokens');
      expect(response.body.tokens).toHaveProperty('accessToken', 'mock-access-token');
      
      expect(RespondToAuthChallengeCommand).toHaveBeenCalledWith({
        ClientId: 'test-client-id',
        ChallengeName: 'SMS_MFA',
        Session: 'mock-session-id',
        ChallengeResponses: {
          SMS_MFA_CODE: '123456'
        }
      });
    });

    it('should handle new password challenge', async () => {
      const mockPasswordResponse = {
        AuthenticationResult: {
          AccessToken: 'mock-access-token',
          RefreshToken: 'mock-refresh-token',
          IdToken: 'mock-id-token'
        }
      };

      mockCognitoClient.send.mockResolvedValue(mockPasswordResponse);

      const response = await request(app)
        .post('/api/auth/respond-to-challenge')
        .send({
          challengeName: 'NEW_PASSWORD_REQUIRED',
          session: 'temp-session-id',
          challengeResponses: {
            NEW_PASSWORD: 'NewPassword123!',
            USERNAME: 'testuser@example.com'
          }
        })
        .expect(200);

      expect(response.body).toHaveProperty('tokens');
      expect(response.body.tokens).toHaveProperty('accessToken', 'mock-access-token');
    });

    it('should reject challenge response with missing parameters', async () => {
      const response = await request(app)
        .post('/api/auth/respond-to-challenge')
        .send({
          challengeName: 'SMS_MFA'
        })
        .expect(400);

      expect(response.body).toHaveProperty('error', 'Missing required parameters');
      expect(mockCognitoClient.send).not.toHaveBeenCalled();
    });

    it('should handle invalid MFA code', async () => {
      const invalidCodeError = new Error('Invalid code provided');
      invalidCodeError.name = 'CodeMismatchException';
      mockCognitoClient.send.mockRejectedValue(invalidCodeError);

      const response = await request(app)
        .post('/api/auth/respond-to-challenge')
        .send({
          challengeName: 'SMS_MFA',
          session: 'mock-session-id',
          challengeResponses: {
            SMS_MFA_CODE: '000000'
          }
        })
        .expect(400);

      expect(response.body).toHaveProperty('error', 'Invalid verification code');
    });
  });

  describe('Route Structure and Security', () => {
    it('should have all required authentication endpoints', () => {
      const router = require('../../../routes/auth');
      
      expect(router).toBeDefined();
      expect(typeof router).toBe('function');
      expect(router.stack).toBeDefined();
      expect(router.stack.length).toBeGreaterThan(0);
    });

    it('should return consistent JSON response format', async () => {
      const mockAuthResponse = {
        AuthenticationResult: {
          AccessToken: 'mock-access-token',
          RefreshToken: 'mock-refresh-token',
          IdToken: 'mock-id-token'
        }
      };

      mockCognitoClient.send.mockResolvedValue(mockAuthResponse);

      const response = await request(app)
        .post('/api/auth/login')
        .send({
          username: 'testuser@example.com',
          password: 'TestPassword123!'
        })
        .expect(200);

      expect(response.headers['content-type']).toMatch(/application\/json/);
      expect(typeof response.body).toBe('object');
    });

    it('should handle malformed JSON requests', async () => {
      const response = await request(app)
        .post('/api/auth/login')
        .set('Content-Type', 'application/json')
        .send('{"invalid": json}')
        .expect(400);

      expect(response.body).toHaveProperty('error');
    });

    it('should validate Content-Type header', async () => {
      const response = await request(app)
        .post('/api/auth/login')
        .set('Content-Type', 'text/plain')
        .send('username=test&password=test')
        .expect(400);

      expect(response.body).toHaveProperty('error');
    });
  });

  describe('Error Handling', () => {
    it('should handle AWS service errors gracefully', async () => {
      const serviceError = new Error('Service temporarily unavailable');
      serviceError.name = 'InternalErrorException';
      mockCognitoClient.send.mockRejectedValue(serviceError);

      const response = await request(app)
        .post('/api/auth/login')
        .send({
          username: 'testuser@example.com',
          password: 'TestPassword123!'
        })
        .expect(503);

      expect(response.body).toHaveProperty('error', 'Service temporarily unavailable');
    });

    it('should handle rate limiting errors', async () => {
      const rateLimitError = new Error('Rate exceeded');
      rateLimitError.name = 'TooManyRequestsException';
      mockCognitoClient.send.mockRejectedValue(rateLimitError);

      const response = await request(app)
        .post('/api/auth/login')
        .send({
          username: 'testuser@example.com',
          password: 'TestPassword123!'
        })
        .expect(429);

      expect(response.body).toHaveProperty('error', 'Too many requests');
    });

    it('should not expose sensitive information in errors', async () => {
      const internalError = new Error('Internal database connection failed with credentials user:pass@host');
      mockCognitoClient.send.mockRejectedValue(internalError);

      const response = await request(app)
        .post('/api/auth/login')
        .send({
          username: 'testuser@example.com',
          password: 'TestPassword123!'
        });

      expect(response.body.error).not.toContain('user:pass@host');
      expect(response.body.error).not.toContain('credentials');
    });
  });
});