/**
 * AWS Cognito Authentication Real Integration Tests
 * Tests actual AWS Cognito integration with real infrastructure
 */

import { describe, it, expect, beforeAll, afterAll, beforeEach, afterEach } from 'vitest';
import AWS from 'aws-sdk';
import { 
  CognitoIdentityProviderClient,
  AdminCreateUserCommand,
  AdminDeleteUserCommand,
  AdminSetUserPasswordCommand,
  AdminInitiateAuthCommand,
  ListUsersCommand
} from '@aws-sdk/client-cognito-identity-provider';

// AWS Configuration from environment
const AWS_REGION = process.env.AWS_REGION || 'us-east-1';
const COGNITO_USER_POOL_ID = process.env.COGNITO_USER_POOL_ID;
const COGNITO_CLIENT_ID = process.env.COGNITO_CLIENT_ID;
const COGNITO_CLIENT_SECRET = process.env.COGNITO_CLIENT_SECRET;

// Test user configuration
const TEST_USER_EMAIL = `test-user-${Date.now()}@example.com`;
const TEST_USERNAME = `testuser${Date.now()}`;
const TEST_PASSWORD = 'TempPassword123!';
const PERMANENT_PASSWORD = 'SecurePassword123!';

describe('AWS Cognito Real Integration Tests', () => {
  let cognitoClient;
  let testUserId;

  beforeAll(async () => {
    // Skip tests if AWS credentials not configured
    if (!COGNITO_USER_POOL_ID || !COGNITO_CLIENT_ID) {
      console.warn('⚠️ Skipping Cognito tests - AWS configuration missing');
      return;
    }

    // Initialize Cognito client
    cognitoClient = new CognitoIdentityProviderClient({
      region: AWS_REGION,
      credentials: {
        accessKeyId: process.env.AWS_ACCESS_KEY_ID,
        secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY
      }
    });

    // Verify connection to Cognito
    try {
      const listUsersCommand = new ListUsersCommand({
        UserPoolId: COGNITO_USER_POOL_ID,
        Limit: 1
      });
      await cognitoClient.send(listUsersCommand);
      console.log('✅ Connected to AWS Cognito User Pool');
    } catch (error) {
      console.error('❌ Failed to connect to Cognito:', error.message);
      throw new Error('Cognito connection failed - check AWS credentials and User Pool ID');
    }
  });

  afterAll(async () => {
    if (!cognitoClient || !testUserId) return;

    try {
      // Clean up test user
      const deleteCommand = new AdminDeleteUserCommand({
        UserPoolId: COGNITO_USER_POOL_ID,
        Username: testUserId
      });
      await cognitoClient.send(deleteCommand);
      console.log(`🧹 Cleaned up test user: ${testUserId}`);
    } catch (error) {
      console.warn(`⚠️ Failed to cleanup test user: ${error.message}`);
    }
  });

  describe('User Registration Flow', () => {
    it('creates user in Cognito User Pool', async () => {
      if (!cognitoClient) return;

      const createUserCommand = new AdminCreateUserCommand({
        UserPoolId: COGNITO_USER_POOL_ID,
        Username: TEST_USERNAME,
        UserAttributes: [
          { Name: 'email', Value: TEST_USER_EMAIL },
          { Name: 'email_verified', Value: 'true' }
        ],
        TemporaryPassword: TEST_PASSWORD,
        MessageAction: 'SUPPRESS'
      });

      const response = await cognitoClient.send(createUserCommand);
      testUserId = response.User.Username;

      expect(response.User).toBeDefined();
      expect(response.User.Username).toBe(TEST_USERNAME);
      expect(response.User.UserStatus).toBe('FORCE_CHANGE_PASSWORD');
      expect(response.User.Enabled).toBe(true);

      // Verify user attributes
      const emailAttr = response.User.Attributes.find(attr => attr.Name === 'email');
      expect(emailAttr.Value).toBe(TEST_USER_EMAIL);
    });

    it('sets permanent password for user', async () => {
      if (!cognitoClient || !testUserId) return;

      const setPasswordCommand = new AdminSetUserPasswordCommand({
        UserPoolId: COGNITO_USER_POOL_ID,
        Username: testUserId,
        Password: PERMANENT_PASSWORD,
        Permanent: true
      });

      await expect(cognitoClient.send(setPasswordCommand)).resolves.not.toThrow();

      // Verify user status changed to CONFIRMED
      const listUsersCommand = new ListUsersCommand({
        UserPoolId: COGNITO_USER_POOL_ID,
        Filter: `username = "${testUserId}"`
      });

      const listResponse = await cognitoClient.send(listUsersCommand);
      const user = listResponse.Users[0];
      expect(user.UserStatus).toBe('CONFIRMED');
    });
  });

  describe('Authentication Flow', () => {
    it('authenticates user with valid credentials', async () => {
      if (!cognitoClient || !testUserId) return;

      const authCommand = new AdminInitiateAuthCommand({
        UserPoolId: COGNITO_USER_POOL_ID,
        ClientId: COGNITO_CLIENT_ID,
        AuthFlow: 'ADMIN_NO_SRP_AUTH',
        AuthParameters: {
          USERNAME: testUserId,
          PASSWORD: PERMANENT_PASSWORD,
          SECRET_HASH: COGNITO_CLIENT_SECRET ? 
            await generateSecretHash(testUserId, COGNITO_CLIENT_ID, COGNITO_CLIENT_SECRET) : 
            undefined
        }
      });

      const authResponse = await cognitoClient.send(authCommand);

      expect(authResponse.AuthenticationResult).toBeDefined();
      expect(authResponse.AuthenticationResult.AccessToken).toBeDefined();
      expect(authResponse.AuthenticationResult.IdToken).toBeDefined();
      expect(authResponse.AuthenticationResult.RefreshToken).toBeDefined();
      expect(authResponse.AuthenticationResult.TokenType).toBe('Bearer');
      expect(authResponse.AuthenticationResult.ExpiresIn).toBeGreaterThan(0);

      console.log('✅ User authentication successful');
    });

    it('rejects invalid credentials', async () => {
      if (!cognitoClient || !testUserId) return;

      const authCommand = new AdminInitiateAuthCommand({
        UserPoolId: COGNITO_USER_POOL_ID,
        ClientId: COGNITO_CLIENT_ID,
        AuthFlow: 'ADMIN_NO_SRP_AUTH',
        AuthParameters: {
          USERNAME: testUserId,
          PASSWORD: 'WrongPassword123!',
          SECRET_HASH: COGNITO_CLIENT_SECRET ? 
            await generateSecretHash(testUserId, COGNITO_CLIENT_ID, COGNITO_CLIENT_SECRET) : 
            undefined
        }
      });

      await expect(cognitoClient.send(authCommand)).rejects.toThrow('Incorrect username or password');
    });

    it('rejects authentication for non-existent user', async () => {
      if (!cognitoClient) return;

      const authCommand = new AdminInitiateAuthCommand({
        UserPoolId: COGNITO_USER_POOL_ID,
        ClientId: COGNITO_CLIENT_ID,
        AuthFlow: 'ADMIN_NO_SRP_AUTH',
        AuthParameters: {
          USERNAME: 'nonexistent_user',
          PASSWORD: PERMANENT_PASSWORD,
          SECRET_HASH: COGNITO_CLIENT_SECRET ? 
            await generateSecretHash('nonexistent_user', COGNITO_CLIENT_ID, COGNITO_CLIENT_SECRET) : 
            undefined
        }
      });

      await expect(cognitoClient.send(authCommand)).rejects.toThrow('User does not exist');
    });
  });

  describe('User Pool Operations', () => {
    it('lists users in the pool', async () => {
      if (!cognitoClient) return;

      const listUsersCommand = new ListUsersCommand({
        UserPoolId: COGNITO_USER_POOL_ID,
        Limit: 10
      });

      const response = await cognitoClient.send(listUsersCommand);

      expect(response.Users).toBeDefined();
      expect(Array.isArray(response.Users)).toBe(true);
      
      // Should include our test user
      const testUser = response.Users.find(user => user.Username === testUserId);
      expect(testUser).toBeDefined();
      expect(testUser.UserStatus).toBe('CONFIRMED');
    });

    it('handles pagination correctly', async () => {
      if (!cognitoClient) return;

      const listUsersCommand = new ListUsersCommand({
        UserPoolId: COGNITO_USER_POOL_ID,
        Limit: 1
      });

      const response = await cognitoClient.send(listUsersCommand);

      expect(response.Users).toHaveLength(1);
      if (response.PaginationToken) {
        expect(typeof response.PaginationToken).toBe('string');
      }
    });
  });

  describe('Error Handling', () => {
    it('handles invalid User Pool ID gracefully', async () => {
      if (!cognitoClient) return;

      const invalidCommand = new ListUsersCommand({
        UserPoolId: 'us-east-1_INVALID',
        Limit: 1
      });

      await expect(cognitoClient.send(invalidCommand)).rejects.toThrow('User pool does not exist');
    });

    it('handles AWS service errors', async () => {
      if (!cognitoClient) return;

      // Test with invalid client configuration
      const invalidClient = new CognitoIdentityProviderClient({
        region: 'invalid-region',
        credentials: {
          accessKeyId: 'invalid',
          secretAccessKey: 'invalid'
        }
      });

      const command = new ListUsersCommand({
        UserPoolId: COGNITO_USER_POOL_ID,
        Limit: 1
      });

      await expect(invalidClient.send(command)).rejects.toThrow();
    });

    it('handles network connectivity issues', async () => {
      if (!cognitoClient) return;

      // Simulate network timeout by using invalid endpoint
      const timeoutClient = new CognitoIdentityProviderClient({
        region: AWS_REGION,
        endpoint: 'https://cognito-idp.invalid-endpoint.amazonaws.com',
        credentials: {
          accessKeyId: process.env.AWS_ACCESS_KEY_ID,
          secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY
        }
      });

      const command = new ListUsersCommand({
        UserPoolId: COGNITO_USER_POOL_ID,
        Limit: 1
      });

      await expect(timeoutClient.send(command)).rejects.toThrow();
    });
  });

  describe('Infrastructure Validation', () => {
    it('validates Cognito User Pool configuration', async () => {
      if (!cognitoClient) return;

      // Test that the User Pool ID format is correct
      expect(COGNITO_USER_POOL_ID).toMatch(/^[a-z0-9-]+_[A-Za-z0-9]+$/);
      
      // Test that the Client ID format is correct
      expect(COGNITO_CLIENT_ID).toMatch(/^[a-z0-9]+$/);
      
      // Test that region is valid
      expect(AWS_REGION).toMatch(/^[a-z0-9-]+$/);
    });

    it('verifies AWS credentials are properly configured', async () => {
      expect(process.env.AWS_ACCESS_KEY_ID).toBeDefined();
      expect(process.env.AWS_SECRET_ACCESS_KEY).toBeDefined();
      expect(process.env.AWS_ACCESS_KEY_ID).toMatch(/^[A-Z0-9]+$/);
    });

    it('tests AWS service availability', async () => {
      if (!cognitoClient) return;

      // Basic health check by listing users
      const startTime = Date.now();
      const listUsersCommand = new ListUsersCommand({
        UserPoolId: COGNITO_USER_POOL_ID,
        Limit: 1
      });

      await cognitoClient.send(listUsersCommand);
      const responseTime = Date.now() - startTime;

      // Service should respond within reasonable time
      expect(responseTime).toBeLessThan(5000); // 5 seconds
      console.log(`⏱️ Cognito response time: ${responseTime}ms`);
    });
  });
});

// Helper function to generate SECRET_HASH for Cognito authentication
async function generateSecretHash(username, clientId, clientSecret) {
  const crypto = await import('crypto');
  const message = username + clientId;
  return crypto.createHmac('SHA256', clientSecret).update(message).digest('base64');
}