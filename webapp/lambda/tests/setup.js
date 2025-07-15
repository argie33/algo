/**
 * Jest test setup configuration
 */

// Mock AWS SDK
jest.mock('@aws-sdk/client-secrets-manager', () => ({
  SecretsManagerClient: jest.fn(() => ({
    send: jest.fn()
  })),
  GetSecretValueCommand: jest.fn()
}));

// Mock database client
jest.mock('pg', () => ({
  Client: jest.fn(() => ({
    connect: jest.fn(),
    query: jest.fn(),
    end: jest.fn()
  }))
}));

// Mock authentication middleware
jest.mock('../middleware/auth', () => ({
  authenticateToken: (req, res, next) => {
    const authHeader = req.headers.authorization;
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return res.status(401).json({ error: 'Authentication required' });
    }
    
    // Mock user for testing
    req.user = {
      userId: 'test-user-123',
      email: 'test@example.com'
    };
    
    next();
  }
}));

// Global test setup
beforeAll(() => {
  // Set test environment variables
  process.env.NODE_ENV = 'test';
  process.env.DB_SECRET_ARN = 'mock-secret-arn';
  process.env.WEBAPP_AWS_REGION = 'us-east-1';
});

afterAll(() => {
  // Cleanup
  jest.clearAllMocks();
});