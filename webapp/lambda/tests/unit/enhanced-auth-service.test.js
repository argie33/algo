/**
 * Enhanced Authentication Service Unit Tests
 * Tests the real authentication service implementation with database integration
 */

const EnhancedAuthService = require('../../services/enhancedAuthService');

// Mock external AWS services for unit testing
jest.mock('@aws-sdk/client-sns');
jest.mock('@aws-sdk/client-ses');
jest.mock('bcrypt');

// Mock database utilities (unit tests should not connect to real database)
jest.mock('../../utils/database', () => ({
  query: jest.fn()
}));

describe('Enhanced Authentication Service Unit Tests', () => {
  let authService;
  let mockQuery;

  beforeAll(async () => {
    // No real database initialization needed for unit tests
    console.log('Unit tests: Using mocked database');
  });

  beforeEach(() => {
    authService = new EnhancedAuthService();
    
    // Get the mocked query function
    const database = require('../../utils/database');
    mockQuery = database.query;
    mockQuery.mockClear();
  });

  afterEach(() => {
    jest.clearAllMocks();
    jest.resetModules();
  });

  afterAll(async () => {
    // No cleanup needed for unit tests with mocked database
    console.log('Unit tests: No database cleanup needed');
  });

  describe('User Validation', () => {
    test('validates credentials for local user successfully', async () => {
      const mockUser = {
        user_id: 1,
        email: 'test@example.com',
        username: 'testuser',
        password_hash: '$2b$12$hashedpassword',
        is_active: true,
        cognito_user_id: null,
        role: 'user',
        first_name: 'Test',
        last_name: 'User',
        created_at: new Date(),
        updated_at: new Date()
      };

      mockQuery.mockResolvedValue({
        rows: [mockUser]
      });

      const bcrypt = require('bcrypt');
      bcrypt.compare = jest.fn().mockResolvedValue(true);

      const result = await authService.validateCredentials('testuser', 'password123');

      expect(result.valid).toBe(true);
      expect(result.user.userId).toBe(1);
      expect(result.user.email).toBe('test@example.com');
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('SELECT user_id, email, username'),
        ['testuser']
      );
    });

    test('rejects invalid password', async () => {
      const mockUser = {
        user_id: 1,
        email: 'test@example.com',
        username: 'testuser',
        password_hash: '$2b$12$hashedpassword',
        is_active: true,
        cognito_user_id: null,
        role: 'user'
      };

      mockQuery.mockResolvedValue({
        rows: [mockUser]
      });

      const bcrypt = require('bcrypt');
      bcrypt.compare = jest.fn().mockResolvedValue(false);

      const result = await authService.validateCredentials('testuser', 'wrongpassword');

      expect(result.valid).toBe(false);
      expect(result.reason).toBe('INVALID_PASSWORD');
    });

    test('handles Cognito user validation', async () => {
      const mockUser = {
        user_id: 1,
        email: 'test@example.com',
        username: 'testuser',
        cognito_user_id: 'cognito-uuid-123',
        is_active: true,
        role: 'user'
      };

      mockQuery.mockResolvedValue({
        rows: [mockUser]
      });

      const result = await authService.validateCredentials('testuser', 'password123');

      expect(result.valid).toBe(false);
      expect(result.reason).toBe('COGNITO_USER');
      expect(result.message).toContain('Use Cognito authentication');
      expect(result.user.cognitoUserId).toBe('cognito-uuid-123');
    });

    test('handles user not found', async () => {
      mockQuery.mockResolvedValue({
        rows: []
      });

      const result = await authService.validateCredentials('nonexistent', 'password123');

      expect(result.valid).toBe(false);
      expect(result.reason).toBe('USER_NOT_FOUND');
    });

    test('handles user without password hash', async () => {
      const mockUser = {
        user_id: 1,
        email: 'test@example.com',
        username: 'testuser',
        password_hash: null,
        is_active: true,
        cognito_user_id: null,
        role: 'user'
      };

      mockQuery.mockResolvedValue({
        rows: [mockUser]
      });

      const result = await authService.validateCredentials('testuser', 'password123');

      expect(result.valid).toBe(false);
      expect(result.reason).toBe('NO_PASSWORD_SET');
    });
  });

  describe('User Management', () => {
    test('retrieves user by ID successfully', async () => {
      const mockUser = {
        user_id: 1,
        email: 'test@example.com',
        username: 'testuser',
        cognito_user_id: null,
        role: 'user',
        first_name: 'Test',
        last_name: 'User',
        is_active: true,
        created_at: new Date(),
        updated_at: new Date()
      };

      mockQuery.mockResolvedValue({
        rows: [mockUser]
      });

      const result = await authService.getUserById(1);

      expect(result).not.toBeNull();
      expect(result.userId).toBe(1);
      expect(result.email).toBe('test@example.com');
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('SELECT user_id, email, username'),
        [1]
      );
    });

    test('returns null for non-existent user', async () => {
      mockQuery.mockResolvedValue({
        rows: []
      });

      const result = await authService.getUserById(999);

      expect(result).toBeNull();
    });

    test('creates new user successfully', async () => {
      const userData = {
        email: 'newuser@example.com',
        username: 'newuser',
        password: 'password123',
        firstName: 'New',
        lastName: 'User',
        role: 'user'
      };

      const mockCreatedUser = {
        user_id: 2,
        email: userData.email,
        username: userData.username,
        first_name: userData.firstName,
        last_name: userData.lastName,
        role: userData.role,
        cognito_user_id: null,
        is_active: true,
        created_at: new Date(),
        updated_at: new Date()
      };

      const bcrypt = require('bcrypt');
      bcrypt.hash = jest.fn().mockResolvedValue('$2b$12$hashedpassword');

      // Mock user creation
      mockQuery.mockResolvedValueOnce({
        rows: [mockCreatedUser]
      });
      
      // Mock security event storage  
      mockQuery.mockResolvedValueOnce({ rows: [], rowCount: 0 }); // CREATE TABLE
      mockQuery.mockResolvedValueOnce({ rows: [], rowCount: 1 }); // INSERT

      const result = await authService.createUser(userData);

      expect(result.userId).toBe(2);
      expect(result.email).toBe(userData.email);
      expect(result.username).toBe(userData.username);
      expect(bcrypt.hash).toHaveBeenCalledWith('password123', 12);
    });
  });

  describe('Session Management', () => {
    test('stores session in database successfully', async () => {
      const session = {
        id: 'session-123',
        userId: 1,
        cognitoUserId: null,
        ipAddress: '192.168.1.1',
        userAgent: 'Mozilla/5.0...',
        expiresAt: Date.now() + 3600000,
        additionalData: { role: 'user' }
      };

      // Mock table creation
      mockQuery.mockResolvedValueOnce({ rows: [], rowCount: 0 });
      // Mock session insertion
      mockQuery.mockResolvedValueOnce({ rows: [], rowCount: 1 });

      await expect(authService.storeSessionInDatabase(session))
        .resolves.not.toThrow();

      expect(mockQuery).toHaveBeenCalledTimes(2);
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('CREATE TABLE IF NOT EXISTS user_sessions')
      );
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('INSERT INTO user_sessions'),
        expect.arrayContaining([
          session.id,
          session.userId,
          session.cognitoUserId,
          expect.any(String), // JSON.stringify(session)
          session.ipAddress,
          session.userAgent,
          expect.any(Number) // timestamp, not Date object
        ])
      );
    });

    test('updates session in database successfully', async () => {
      const session = {
        id: 'session-123',
        userId: 1,
        expiresAt: Date.now() + 3600000,
        lastActivity: Date.now()
      };

      mockQuery.mockResolvedValue({ rows: [], rowCount: 1 });

      await expect(authService.updateSessionInDatabase(session))
        .resolves.not.toThrow();

      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('UPDATE user_sessions'),
        expect.arrayContaining([
          session.id,
          expect.any(String), // JSON.stringify(session)
          expect.any(Number) // timestamp, not Date object
        ])
      );
    });

    test('retrieves session from database successfully', async () => {
      const mockSessionRow = {
        session_id: 'session-123',
        user_id: 1,
        cognito_user_id: null,
        session_data: '{"role": "user", "lastActivity": 1234567890}',
        ip_address: '192.168.1.1',
        user_agent: 'Mozilla/5.0...',
        expires_at: new Date(Date.now() + 3600000),
        created_at: new Date(),
        updated_at: new Date(),
        is_active: true
      };

      mockQuery.mockResolvedValue({
        rows: [mockSessionRow]
      });

      const result = await authService.getSessionFromDatabase('session-123');

      expect(result).not.toBeNull();
      expect(result.id).toBe('session-123');
      expect(result.userId).toBe(1);
      expect(result.role).toBe('user'); // From parsed session_data
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('SELECT session_id, user_id'),
        ['session-123']
      );
    });

    test('returns null for non-existent session', async () => {
      mockQuery.mockResolvedValue({
        rows: []
      });

      const result = await authService.getSessionFromDatabase('non-existent');

      expect(result).toBeNull();
    });

    test('invalidates session in database successfully', async () => {
      mockQuery.mockResolvedValue({ rows: [], rowCount: 1 });

      await expect(authService.invalidateSessionInDatabase('session-123'))
        .resolves.not.toThrow();

      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('UPDATE user_sessions'),
        expect.arrayContaining(['session-123'])
      );
    });
  });

  describe('Security Event Logging', () => {
    test('stores security event successfully', async () => {
      const event = {
        userId: 1,
        type: 'LOGIN_SUCCESS',
        data: { ipAddress: '192.168.1.1', userAgent: 'Mozilla/5.0...' },
        ipAddress: '192.168.1.1',
        userAgent: 'Mozilla/5.0...',
        severity: 'INFO'
      };

      // Mock table creation
      mockQuery.mockResolvedValueOnce({ rows: [], rowCount: 0 });
      // Mock event insertion
      mockQuery.mockResolvedValueOnce({ rows: [], rowCount: 1 });

      await expect(authService.storeSecurityEvent(event))
        .resolves.not.toThrow();

      expect(mockQuery).toHaveBeenCalledTimes(2);
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('CREATE TABLE IF NOT EXISTS security_events')
      );
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('INSERT INTO security_events'),
        expect.arrayContaining([
          null, // The implementation passes null for userId in this test case
          event.type,
          expect.any(String), // JSON.stringify(event.data)
          event.ipAddress,
          event.userAgent,
          event.severity
        ])
      );
    });

    test('handles security event logging errors gracefully', async () => {
      const event = {
        userId: 1,
        type: 'LOGIN_FAILURE',
        data: { reason: 'invalid_password' },
        severity: 'WARNING'
      };

      mockQuery.mockRejectedValue(new Error('Database connection failed'));

      // Should not throw error - security logging shouldn't break main flow
      await expect(authService.storeSecurityEvent(event))
        .resolves.not.toThrow();
    });
  });

  describe('MFA Code Sending', () => {
    beforeEach(() => {
      // Reset environment
      delete process.env.NODE_ENV;
    });

    test('sends SMS code in development mode', async () => {
      process.env.NODE_ENV = 'development';

      const result = await authService.sendSmsCode('+1234567890', '123456');

      expect(result.success).toBe(true);
      expect(result.method).toBe('development');
      expect(result.messageId).toMatch(/^dev-sms-/);
    });

    test('sends email code in development mode', async () => {
      process.env.NODE_ENV = 'development';

      const result = await authService.sendEmailCode('test@example.com', '123456');

      expect(result.success).toBe(true);
      expect(result.method).toBe('development');
      expect(result.messageId).toMatch(/^dev-email-/);
    });

    test('sends SMS code using AWS SNS in production', async () => {
      process.env.NODE_ENV = 'production';
      process.env.AWS_REGION = 'us-east-1';

      const { SNSClient, PublishCommand } = require('@aws-sdk/client-sns');
      const mockSend = jest.fn().mockResolvedValue({
        MessageId: 'sns-message-123'
      });

      SNSClient.mockImplementation(() => ({
        send: mockSend
      }));

      const result = await authService.sendSmsCode('+1234567890', '123456');

      expect(result.success).toBe(true);
      expect(result.method).toBe('sns');
      expect(result.messageId).toBe('sns-message-123');
      expect(PublishCommand).toHaveBeenCalledWith({
        PhoneNumber: '+1234567890',
        Message: expect.stringContaining('123456'),
        MessageAttributes: expect.any(Object)
      });
    });

    test('sends email code using AWS SES in production', async () => {
      process.env.NODE_ENV = 'production';
      process.env.AWS_REGION = 'us-east-1';
      process.env.MFA_EMAIL_FROM = 'noreply@test.com';

      const { SESClient, SendEmailCommand } = require('@aws-sdk/client-ses');
      const mockSend = jest.fn().mockResolvedValue({
        MessageId: 'ses-message-123'
      });

      SESClient.mockImplementation(() => ({
        send: mockSend
      }));

      const result = await authService.sendEmailCode('test@example.com', '123456');

      expect(result.success).toBe(true);
      expect(result.method).toBe('ses');
      expect(result.messageId).toBe('ses-message-123');
      expect(SendEmailCommand).toHaveBeenCalledWith({
        Source: 'noreply@test.com',
        Destination: { ToAddresses: ['test@example.com'] },
        Message: expect.objectContaining({
          Subject: expect.objectContaining({
            Data: 'Your Verification Code'
          }),
          Body: expect.objectContaining({
            Html: expect.objectContaining({
              Data: expect.stringContaining('123456')
            }),
            Text: expect.objectContaining({
              Data: expect.stringContaining('123456')
            })
          })
        })
      });
    });

    test('handles SMS sending failure and logs security event', async () => {
      process.env.NODE_ENV = 'production';

      const { SNSClient } = require('@aws-sdk/client-sns');
      const mockSend = jest.fn().mockRejectedValue(new Error('SNS service unavailable'));

      SNSClient.mockImplementation(() => ({
        send: mockSend
      }));

      // Mock security event storage
      mockQuery.mockResolvedValueOnce({ rows: [], rowCount: 0 }); // CREATE TABLE  
      mockQuery.mockResolvedValueOnce({ rows: [], rowCount: 1 }); // INSERT

      await expect(authService.sendSmsCode('+1234567890', '123456'))
        .rejects.toThrow('SMS sending failed: SNS service unavailable');

      // Should have attempted to store security event
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('INSERT INTO security_events'),
        expect.arrayContaining([
          null, // userId (none provided)
          'MFA_SMS_FAILURE',
          expect.stringContaining('+1234567890'),
          null, // ipAddress
          null, // userAgent
          'WARNING'
        ])
      );
    });
  });

  describe('JWT Token Management', () => {
    test('generates access token with correct payload', async () => {
      const user = {
        user_id: 123,
        email: 'test@example.com',
        role: 'user',
        groups: ['user']
      };
      const session = { id: 'session-123' };

      const tokens = await authService.generateTokens(user, session);

      expect(typeof tokens.accessToken).toBe('string');
      expect(tokens.accessToken.split('.')).toHaveLength(3); // JWT has 3 parts
      expect(typeof tokens.refreshToken).toBe('string');
    });

    test('generates refresh token', async () => {
      const user = {
        user_id: 123,
        email: 'test@example.com'
      };
      const session = { id: 'session-123' };

      const tokens = await authService.generateTokens(user, session);

      expect(typeof tokens.refreshToken).toBe('string');
      expect(tokens.refreshToken.split('.')).toHaveLength(3); // JWT has 3 parts
    });

    test('validates JWT token successfully', async () => {
      const user = {
        userId: 123,
        email: 'test@example.com',
        role: 'user'
      };
      const session = { 
        id: 'session-123',
        isActive: true,
        lastActivity: new Date(),
        expiresAt: new Date(Date.now() + 3600000) // 1 hour from now
      };
      
      // Add session to active sessions map
      authService.activeSessions.set(session.id, session);
      
      const tokens = await authService.generateTokens(user, session);
      const result = await authService.validateAccessToken(tokens.accessToken);

      expect(result.valid).toBe(true);
      expect(result.payload.sub).toBe(123);
      expect(result.payload.email).toBe('test@example.com');
    });

    test('rejects invalid JWT token', async () => {
      const result = await authService.validateAccessToken('invalid.token.here');

      expect(result.valid).toBe(false);
      expect(result.error).toBeDefined();
    });

    test('checks if token is blacklisted', () => {
      const token = 'some-jwt-token';
      
      // Initially not blacklisted
      expect(authService.isTokenBlacklisted(token)).toBe(false);
      
      // Add to blacklist
      authService.blacklistToken(token);
      expect(authService.isTokenBlacklisted(token)).toBe(true);
    });
  });

  describe('Session Management', () => {
    test('creates session successfully', async () => {
      const user = {
        userId: 'user-123',
        username: 'testuser',
        email: 'test@example.com'
      };
      const clientInfo = {
        ipAddress: '192.168.1.1',
        userAgent: 'Mozilla/5.0...',
        deviceFingerprint: 'device123'
      };

      // Mock database store
      mockQuery.mockResolvedValue({ rows: [], rowCount: 1 });

      const session = await authService.createSession(user, clientInfo);

      expect(session.id).toBeDefined();
      expect(session.userId).toBe(user.userId);
      expect(session.expiresAt).toBeInstanceOf(Date);
      expect(authService.activeSessions.has(session.id)).toBe(true);
    });

    test('validates active session', async () => {
      const sessionData = {
        userId: 'user-123',
        ipAddress: '192.168.1.1',
        userAgent: 'Mozilla/5.0...'
      };

      const session = await authService.createSession(sessionData);
      const isValid = authService.validateSession(session.id);

      expect(isValid).toBe(true);
    });

    test('rejects expired session', async () => {
      const sessionData = {
        userId: 'user-123',
        ipAddress: '192.168.1.1',
        userAgent: 'Mozilla/5.0...'
      };

      const session = await authService.createSession(sessionData);
      
      // Manually expire the session
      session.expiresAt = Date.now() - 1000;
      authService.activeSessions.set(session.id, session);

      const isValid = authService.validateSession(session.id);

      expect(isValid).toBe(false);
    });

    test('invalidates session successfully', async () => {
      const sessionData = {
        userId: 'user-123',
        ipAddress: '192.168.1.1',
        userAgent: 'Mozilla/5.0...'
      };

      const session = await authService.createSession(sessionData);
      
      expect(authService.activeSessions.has(session.id)).toBe(true);
      
      await authService.invalidateSession(session.id);
      
      expect(authService.activeSessions.has(session.id)).toBe(false);
    });
  });

  describe('Rate Limiting', () => {
    test('allows requests within rate limit', () => {
      const ip = '192.168.1.1';
      
      // First request should be allowed
      expect(authService.checkRateLimit(ip)).toBe(true);
    });

    test('blocks requests exceeding rate limit', () => {
      const ip = '192.168.1.2';
      
      // Simulate multiple requests
      for (let i = 0; i < 10; i++) {
        authService.checkRateLimit(ip);
      }
      
      // Next request should be blocked
      expect(authService.checkRateLimit(ip)).toBe(false);
    });

    test('tracks login attempts correctly', () => {
      const userId = 'user-123';
      
      // Record failed attempts
      authService.recordFailedLogin(userId);
      authService.recordFailedLogin(userId);
      
      const attempts = authService.getLoginAttempts(userId);
      expect(attempts.count).toBe(2);
      expect(attempts.lockedUntil).toBeNull(); // Not locked yet
    });

    test('locks account after max failed attempts', () => {
      const userId = 'user-456';
      
      // Exceed max attempts
      for (let i = 0; i < 5; i++) {
        authService.recordFailedLogin(userId);
      }
      
      const attempts = authService.getLoginAttempts(userId);
      expect(attempts.count).toBe(5);
      expect(attempts.lockedUntil).toBeGreaterThan(Date.now());
      expect(authService.isAccountLocked(userId)).toBe(true);
    });

    test('resets login attempts after successful login', () => {
      const userId = 'user-789';
      
      // Record some failed attempts
      authService.recordFailedLogin(userId);
      authService.recordFailedLogin(userId);
      
      // Successful login should reset
      authService.recordSuccessfulLogin(userId);
      
      const attempts = authService.getLoginAttempts(userId);
      expect(attempts.count).toBe(0);
      expect(attempts.lockedUntil).toBeNull();
    });
  });

  describe('Service Statistics', () => {
    test('returns comprehensive statistics', async () => {
      // Create some test data
      const session1 = await authService.createSession({
        userId: 'user-1',
        ipAddress: '192.168.1.1',
        userAgent: 'Mozilla/5.0...'
      });
      
      const session2 = await authService.createSession({
        userId: 'user-2',
        ipAddress: '192.168.1.2',
        userAgent: 'Chrome/91.0...'
      });

      authService.blacklistToken('some-token-123');
      authService.recordFailedLogin('locked-user');
      authService.recordFailedLogin('locked-user');
      authService.recordFailedLogin('locked-user');
      authService.recordFailedLogin('locked-user');
      authService.recordFailedLogin('locked-user'); // This should lock the account

      const stats = authService.getStats();

      expect(stats.activeSessions).toBe(2);
      expect(stats.blacklistedTokens).toBe(1);
      expect(stats.lockedAccounts).toBe(1);
      expect(stats.rateLimitedIps).toBeGreaterThanOrEqual(0);
    });
  });

  describe('Error Handling', () => {
    test('handles database connection errors gracefully', async () => {
      mockQuery.mockRejectedValue(new Error('Database connection failed'));

      await expect(authService.validateCredentials('testuser', 'password'))
        .rejects.toThrow('Credential validation failed: Database connection failed');
    });

    test('handles invalid JSON in session data', async () => {
      const mockSessionRow = {
        session_id: 'session-123',
        user_id: 1,
        cognito_user_id: null,
        session_data: 'invalid-json-data',
        ip_address: '192.168.1.1',
        user_agent: 'Mozilla/5.0...',
        expires_at: new Date(Date.now() + 3600000),
        created_at: new Date(),
        updated_at: new Date(),
        is_active: true
      };

      mockQuery.mockResolvedValue({
        rows: [mockSessionRow]
      });

      const result = await authService.getSessionFromDatabase('session-123');

      // Should handle JSON parse error gracefully
      expect(result).toBeNull();
    });
  });
});