/**
 * INTEGRATION TESTS: Authentication and Authorization
 * Industry Standard: Tests real AWS Cognito integration
 * Uses IaC-deployed test infrastructure with proper setup/teardown
 */

const { CognitoIdentityProviderClient, AdminCreateUserCommand, AdminSetUserPasswordCommand, AdminGetUserCommand, AdminDeleteUserCommand, AdminInitiateAuthCommand, AdminUpdateUserAttributesCommand } = require('@aws-sdk/client-cognito-identity-provider');
const jwt = require('jsonwebtoken');

const describeOrSkip = (process.env.TEST_USER_POOL_ID && process.env.TEST_USER_POOL_CLIENT_ID) ? describe : describe.skip;

describeOrSkip('Authentication Integration Tests (Industry Standard)', () => {
  let cognitoClient;
  let userPoolId;
  let userPoolClientId;
  let testUsers = [];

  beforeAll(async () => {
    // Load test infrastructure configuration
    const region = process.env.AWS_REGION || 'us-east-1';
    cognitoClient = new CognitoIdentityProviderClient({ region });

    // Get Cognito configuration from environment
    userPoolId = process.env.TEST_USER_POOL_ID;
    userPoolClientId = process.env.TEST_USER_POOL_CLIENT_ID;

    if (!userPoolId || !userPoolClientId) {
      console.log('⚠️ Skipping auth integration tests - Cognito infrastructure not available');
      test.skip = true;
      return;
    }

    console.log('✅ Cognito integration test setup completed');
  }, 30000);

  afterAll(async () => {
    // Clean up test users
    if (cognitoClient && userPoolId) {
      for (const user of testUsers) {
        try {
          await cognitoClient.send(new AdminDeleteUserCommand({
            UserPoolId: userPoolId,
            Username: user.username
          }));
        } catch (error) {
          console.warn(`⚠️ Failed to delete test user ${user.username}:`, error.message);
        }
      }
      console.log('✅ Auth integration test cleanup completed');
    }
  });

  describe('Cognito User Pool Operations', () => {
    it('creates and verifies user accounts', async () => {
      const testUser = {
        username: `test-user-${Date.now()}`,
        email: `integration-test-${Date.now()}@example.com`,
        tempPassword: 'TempPass123!',
        finalPassword: 'FinalPass123!'
      };

      // Create user
      const createResult = await cognitoClient.send(new AdminCreateUserCommand({
        UserPoolId: userPoolId,
        Username: testUser.username,
        UserAttributes: [
          {
            Name: 'email',
            Value: testUser.email
          },
          {
            Name: 'email_verified',
            Value: 'true'
          }
        ],
        TemporaryPassword: testUser.tempPassword,
        MessageAction: 'SUPPRESS' // Don't send welcome email in tests
      }));

      testUsers.push(testUser);

      expect(createResult.User).toBeDefined();
      expect(createResult.User.Username).toBe(testUser.username);
      expect(createResult.User.UserStatus).toBe('FORCE_CHANGE_PASSWORD');

      // Set permanent password
      await cognitoClient.send(new AdminSetUserPasswordCommand({
        UserPoolId: userPoolId,
        Username: testUser.username,
        Password: testUser.finalPassword,
        Permanent: true
      }));

      // Verify user exists
      const getResult = await cognitoClient.send(new AdminGetUserCommand({
        UserPoolId: userPoolId,
        Username: testUser.username
      }));

      expect(getResult.Username).toBe(testUser.username);
      expect(getResult.UserStatus).toBe('CONFIRMED');
    });

    it('authenticates users and generates JWT tokens', async () => {
      const testUser = {
        username: `auth-test-${Date.now()}`,
        email: `auth-test-${Date.now()}@example.com`,
        password: 'AuthTest123!'
      };

      // Create and confirm user
      await cognitoClient.send(new AdminCreateUserCommand({
        UserPoolId: userPoolId,
        Username: testUser.username,
        UserAttributes: [
          { Name: 'email', Value: testUser.email },
          { Name: 'email_verified', Value: 'true' }
        ],
        TemporaryPassword: testUser.password,
        MessageAction: 'SUPPRESS'
      }));

      await cognitoClient.send(new AdminSetUserPasswordCommand({
        UserPoolId: userPoolId,
        Username: testUser.username,
        Password: testUser.password,
        Permanent: true
      }));

      testUsers.push(testUser);

      // Authenticate user
      const authResult = await cognitoClient.send(new AdminInitiateAuthCommand({
        UserPoolId: userPoolId,
        ClientId: userPoolClientId,
        AuthFlow: 'ADMIN_NO_SRP_AUTH',
        AuthParameters: {
          USERNAME: testUser.username,
          PASSWORD: testUser.password
        }
      }));

      expect(authResult.AuthenticationResult).toBeDefined();
      expect(authResult.AuthenticationResult.AccessToken).toBeDefined();
      expect(authResult.AuthenticationResult.IdToken).toBeDefined();
      expect(authResult.AuthenticationResult.RefreshToken).toBeDefined();

      // Decode and verify JWT token
      const idToken = authResult.AuthenticationResult.IdToken;
      const decodedToken = jwt.decode(idToken, { complete: true });

      expect(decodedToken.payload.email).toBe(testUser.email);
      expect(decodedToken.payload['cognito:username']).toBe(testUser.username);
      expect(decodedToken.payload.token_use).toBe('id');
    });

    it('handles token refresh operations', async () => {
      const testUser = {
        username: `refresh-test-${Date.now()}`,
        email: `refresh-test-${Date.now()}@example.com`,
        password: 'RefreshTest123!'
      };

      // Create and confirm user
      await cognitoClient.send(new AdminCreateUserCommand({
        UserPoolId: userPoolId,
        Username: testUser.username,
        UserAttributes: [
          { Name: 'email', Value: testUser.email },
          { Name: 'email_verified', Value: 'true' }
        ],
        TemporaryPassword: testUser.password,
        MessageAction: 'SUPPRESS'
      }));

      await cognitoClient.send(new AdminSetUserPasswordCommand({
        UserPoolId: userPoolId,
        Username: testUser.username,
        Password: testUser.password,
        Permanent: true
      }));

      testUsers.push(testUser);

      // Initial authentication
      const authResult = await cognitoClient.send(new AdminInitiateAuthCommand({
        UserPoolId: userPoolId,
        ClientId: userPoolClientId,
        AuthFlow: 'ADMIN_NO_SRP_AUTH',
        AuthParameters: {
          USERNAME: testUser.username,
          PASSWORD: testUser.password
        }
      }));

      const refreshToken = authResult.AuthenticationResult.RefreshToken;

      // Refresh tokens
      const refreshResult = await cognitoClient.send(new AdminInitiateAuthCommand({
        UserPoolId: userPoolId,
        ClientId: userPoolClientId,
        AuthFlow: 'REFRESH_TOKEN_AUTH',
        AuthParameters: {
          REFRESH_TOKEN: refreshToken
        }
      }));

      expect(refreshResult.AuthenticationResult).toBeDefined();
      expect(refreshResult.AuthenticationResult.AccessToken).toBeDefined();
      expect(refreshResult.AuthenticationResult.IdToken).toBeDefined();
      
      // Verify new tokens are different
      expect(refreshResult.AuthenticationResult.AccessToken)
        .not.toBe(authResult.AuthenticationResult.AccessToken);
    });
  });

  describe('Authentication Middleware Integration', () => {
    let validToken;
    let testUser;

    beforeEach(async () => {
      testUser = {
        username: `middleware-test-${Date.now()}`,
        email: `middleware-test-${Date.now()}@example.com`,
        password: 'MiddlewareTest123!'
      };

      // Create user and get token
      await cognitoClient.send(new AdminCreateUserCommand({
        UserPoolId: userPoolId,
        Username: testUser.username,
        UserAttributes: [
          { Name: 'email', Value: testUser.email },
          { Name: 'email_verified', Value: 'true' }
        ],
        TemporaryPassword: testUser.password,
        MessageAction: 'SUPPRESS'
      }));

      await cognitoClient.send(new AdminSetUserPasswordCommand({
        UserPoolId: userPoolId,
        Username: testUser.username,
        Password: testUser.password,
        Permanent: true
      }));

      testUsers.push(testUser);

      const authResult = await cognitoClient.send(new AdminInitiateAuthCommand({
        UserPoolId: userPoolId,
        ClientId: userPoolClientId,
        AuthFlow: 'ADMIN_NO_SRP_AUTH',
        AuthParameters: {
          USERNAME: testUser.username,
          PASSWORD: testUser.password
        }
      }));

      validToken = authResult.AuthenticationResult.IdToken;
    });

    it('validates JWT tokens correctly', async () => {
      // Test with our auth middleware (requires integration with actual middleware)
      const authMiddleware = require('../../middleware/auth');
      
      // Mock request/response for middleware testing
      const mockReq = {
        headers: {
          authorization: `Bearer ${validToken}`
        }
      };
      
      const mockRes = {
        status: jest.fn().mockReturnThis(),
        json: jest.fn()
      };
      
      const mockNext = jest.fn();

      // Set up environment for production mode
      process.env.NODE_ENV = 'production';
      process.env.COGNITO_USER_POOL_ID = userPoolId;
      process.env.COGNITO_CLIENT_ID = userPoolClientId;
      process.env.ALLOW_DEV_AUTH_BYPASS = 'false';

      await authMiddleware(mockReq, mockRes, mockNext);

      // Should call next() for valid token
      expect(mockNext).toHaveBeenCalled();
      expect(mockReq.user).toBeDefined();
      expect(mockReq.user.email).toBe(testUser.email);
    });

    it('rejects invalid tokens', async () => {
      const authMiddleware = require('../../middleware/auth');
      
      const mockReq = {
        headers: {
          authorization: 'Bearer invalid-token'
        }
      };
      
      const mockRes = {
        status: jest.fn().mockReturnThis(),
        json: jest.fn()
      };
      
      const mockNext = jest.fn();

      process.env.NODE_ENV = 'production';
      process.env.ALLOW_DEV_AUTH_BYPASS = 'false';

      await authMiddleware(mockReq, mockRes, mockNext);

      // Should return 401 for invalid token
      expect(mockRes.status).toHaveBeenCalledWith(401);
      expect(mockNext).not.toHaveBeenCalled();
    });

    it('handles missing authorization headers', async () => {
      const authMiddleware = require('../../middleware/auth');
      
      const mockReq = {
        headers: {} // No authorization header
      };
      
      const mockRes = {
        status: jest.fn().mockReturnThis(),
        json: jest.fn()
      };
      
      const mockNext = jest.fn();

      process.env.NODE_ENV = 'production';
      process.env.ALLOW_DEV_AUTH_BYPASS = 'false';

      await authMiddleware(mockReq, mockRes, mockNext);

      expect(mockRes.status).toHaveBeenCalledWith(401);
      expect(mockNext).not.toHaveBeenCalled();
    });
  });

  describe('User Management Operations', () => {
    it('updates user attributes', async () => {
      const testUser = {
        username: `update-test-${Date.now()}`,
        email: `update-test-${Date.now()}@example.com`,
        password: 'UpdateTest123!'
      };

      // Create user
      await cognitoClient.send(new AdminCreateUserCommand({
        UserPoolId: userPoolId,
        Username: testUser.username,
        UserAttributes: [
          { Name: 'email', Value: testUser.email },
          { Name: 'email_verified', Value: 'true' }
        ],
        TemporaryPassword: testUser.password,
        MessageAction: 'SUPPRESS'
      }));

      await cognitoClient.send(new AdminSetUserPasswordCommand({
        UserPoolId: userPoolId,
        Username: testUser.username,
        Password: testUser.password,
        Permanent: true
      }));

      testUsers.push(testUser);

      // Update user attributes
      const newPhoneNumber = '+12345678901';
      await cognitoClient.send(new AdminUpdateUserAttributesCommand({
        UserPoolId: userPoolId,
        Username: testUser.username,
        UserAttributes: [
          {
            Name: 'phone_number',
            Value: newPhoneNumber
          }
        ]
      }));

      // Verify update
      const userResult = await cognitoClient.send(new AdminGetUserCommand({
        UserPoolId: userPoolId,
        Username: testUser.username
      }));

      const phoneAttr = userResult.UserAttributes.find(attr => attr.Name === 'phone_number');
      expect(phoneAttr).toBeDefined();
      expect(phoneAttr.Value).toBe(newPhoneNumber);
    });

    it('handles user deletion', async () => {
      const testUser = {
        username: `delete-test-${Date.now()}`,
        email: `delete-test-${Date.now()}@example.com`,
        password: 'DeleteTest123!'
      };

      // Create user
      await cognitoClient.send(new AdminCreateUserCommand({
        UserPoolId: userPoolId,
        Username: testUser.username,
        UserAttributes: [
          { Name: 'email', Value: testUser.email },
          { Name: 'email_verified', Value: 'true' }
        ],
        TemporaryPassword: testUser.password,
        MessageAction: 'SUPPRESS'
      }));

      // Verify user exists
      const getResult = await cognitoClient.send(new AdminGetUserCommand({
        UserPoolId: userPoolId,
        Username: testUser.username
      }));
      expect(getResult.Username).toBe(testUser.username);

      // Delete user
      await cognitoClient.send(new AdminDeleteUserCommand({
        UserPoolId: userPoolId,
        Username: testUser.username
      }));

      // Verify user is deleted
      await expect(
        cognitoClient.send(new AdminGetUserCommand({
          UserPoolId: userPoolId,
          Username: testUser.username
        }))
      ).rejects.toThrow('UserNotFoundException');
    });
  });

  describe('Error Handling and Security', () => {
    it('handles authentication failures correctly', async () => {
      const invalidUser = {
        username: 'nonexistent-user',
        password: 'WrongPassword123!'
      };

      await expect(
        cognitoClient.send(new AdminInitiateAuthCommand({
          UserPoolId: userPoolId,
          ClientId: userPoolClientId,
          AuthFlow: 'ADMIN_NO_SRP_AUTH',
          AuthParameters: {
            USERNAME: invalidUser.username,
            PASSWORD: invalidUser.password
          }
        }))
      ).rejects.toThrow('UserNotFoundException');
    });

    it('enforces password policies', async () => {
      const testUser = {
        username: `policy-test-${Date.now()}`,
        email: `policy-test-${Date.now()}@example.com`,
        weakPassword: 'weak'
      };

      // Should fail with weak password
      await expect(
        cognitoClient.send(new AdminCreateUserCommand({
          UserPoolId: userPoolId,
          Username: testUser.username,
          UserAttributes: [
            { Name: 'email', Value: testUser.email }
          ],
          TemporaryPassword: testUser.weakPassword,
          MessageAction: 'SUPPRESS'
        }))
      ).rejects.toThrow();
    });

    it('handles rate limiting and throttling', async () => {
      // Test rapid successive requests to trigger throttling
      const rapidRequests = Array.from({ length: 5 }, (_, i) => 
        cognitoClient.send(new AdminGetUserCommand({
          UserPoolId: userPoolId,
          Username: 'nonexistent-user-for-throttling'
        })).catch(error => error)
      );

      const results = await Promise.all(rapidRequests);
      
      // All should fail (user doesn't exist), but shouldn't crash
      results.forEach(result => {
        expect(result).toBeInstanceOf(Error);
      });
    });
  });
});