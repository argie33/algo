// Jest setup file - runs before each test file

// Set test environment
process.env.NODE_ENV = 'test';

// Mock console methods to reduce noise
const originalConsole = { ...console };

beforeAll(() => {
  // Mock console methods to reduce noise in tests
  console.log = jest.fn();
  console.info = jest.fn();
  console.warn = jest.fn();
  console.error = jest.fn();
  console.debug = jest.fn();
});

afterAll(() => {
  // Restore console
  Object.assign(console, originalConsole);
});

// Global test timeout
jest.setTimeout(30000);

// Mock timers by default
beforeEach(() => {
  jest.clearAllMocks();
  jest.clearAllTimers();
});

afterEach(() => {
  jest.runOnlyPendingTimers();
  jest.useRealTimers();
});