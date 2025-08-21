// Global test setup
process.env.NODE_ENV = 'test';
process.env.DB_HOST = 'localhost';
process.env.DB_PORT = '5432';
process.env.DB_NAME = 'test_stocks';
process.env.DB_USER = 'test_user';
process.env.DB_PASSWORD = 'test_password';
process.env.JWT_SECRET = 'test-jwt-secret-key';
process.env.API_KEY_ENCRYPTION_SECRET = 'test-secret-key-for-development-only-32-chars';
process.env.COGNITO_USER_POOL_ID = 'us-east-1_TEST123';
process.env.COGNITO_CLIENT_ID = 'test-client-id';

// Mock AWS SDK
jest.mock('@aws-sdk/client-secrets-manager', () => ({
  SecretsManagerClient: jest.fn().mockImplementation(() => ({
    send: jest.fn().mockResolvedValue({
      SecretString: JSON.stringify({
        host: 'localhost',
        port: 5432,
        username: 'test_user',
        password: 'test_password',
        dbname: 'test_stocks'
      })
    })
  })),
  GetSecretValueCommand: jest.fn()
}));

// Mock Cognito JWT Verifier
jest.mock('aws-jwt-verify', () => ({
  CognitoJwtVerifier: {
    create: jest.fn().mockReturnValue({
      verify: jest.fn().mockResolvedValue({
        sub: 'test-user-id',
        'cognito:username': 'testuser',
        email: 'test@example.com'
      })
    })
  }
}));

// Mock database connection
const mockQuery = jest.fn();
const mockPool = {
  connect: jest.fn().mockResolvedValue({
    query: mockQuery,
    release: jest.fn()
  }),
  end: jest.fn(),
  query: mockQuery
};

jest.mock('pg', () => ({
  Pool: jest.fn().mockImplementation(() => mockPool)
}));

// Global test utilities
global.mockDb = {
  query: mockQuery,
  pool: mockPool,
  resetMocks: () => {
    mockQuery.mockClear();
    mockPool.connect.mockClear();
  }
};

// Console suppression for cleaner test output
const originalError = console.error;
const originalWarn = console.warn;
const originalLog = console.log;

beforeAll(() => {
  console.error = jest.fn();
  console.warn = jest.fn();
  console.log = jest.fn();
});

afterAll(() => {
  console.error = originalError;
  console.warn = originalWarn;
  console.log = originalLog;
});

beforeEach(() => {
  global.mockDb.resetMocks();
});