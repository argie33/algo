// Jest setup file - runs before each test file

// Set test environment FIRST before any imports
process.env.NODE_ENV = "test";
process.env.ALLOW_DEV_BYPASS = "true";
process.env.JWT_SECRET = "test-secret-key-for-testing-only";
process.env.API_KEY_ENCRYPTION_SECRET = "test-encryption-secret-key-for-api-keys-testing-only";

// Mock database setup - no real database connection needed
process.env.DB_HOST = "mock-host";
process.env.DB_USER = "mock-user";
process.env.DB_PASSWORD = "mock-password";
process.env.DB_NAME = "mock-db";
process.env.DB_PORT = "5432";
process.env.DB_SSL = "false";

// Mock the database module with loader-based schemas
jest.mock('../utils/database', () => require('./setup/database').mockDatabaseModule);

// Debug environment variables
console.log("🔧 Test setup - Mock database environment:", {
  NODE_ENV: process.env.NODE_ENV,
  DB_HOST: process.env.DB_HOST,
  MOCK_DATABASE: true
});

// Ensure crypto is available for all tests (fixes ETag generation issues)
Object.defineProperty(global, "crypto", {
  value: {
    createHash: require("crypto").createHash,
    randomBytes: require("crypto").randomBytes,
    pbkdf2: require("crypto").pbkdf2,
    pbkdf2Sync: require("crypto").pbkdf2Sync,
    randomUUID: require("crypto").randomUUID,
  },
  writable: false,
  enumerable: true,
  configurable: false,
});

// Also ensure Node.js crypto module is available
if (!global.process) {
  global.process = process;
}

// Initialize mock database for tests
let db;

// Determine if we need the mock or real database
if (process.env.NODE_ENV === 'test' || process.env.MOCK_DATABASE === 'true') {
  // Use the mock database for integration tests
  db = require("./utils/database.mock");
  console.log("🧪 Using mock database for tests");
} else {
  // Use the real database for other tests
  db = require("../utils/database");
  console.log("🔗 Using real database for tests");
}

// Replace the real database module with our mock for integration tests
jest.doMock("../utils/database", () => db);

// Mark database as available for all tests
global.DATABASE_AVAILABLE = () => true;
global.TEST_DB = db;

beforeAll(async () => {
  console.log("✅ Using mock database with loader-based schemas for testing");

  // Initialize mock database - no real connection needed
  try {
    console.log("🔄 Initializing mock database...");

    // Mock database initialization always succeeds
    await db.initializeDatabase();

    // Test the mock query functionality
    const testResult = await db.query("SELECT 1 as test");

    if (!testResult || !testResult.rows) {
      throw new Error("Mock database query test failed");
    }

    console.log("✅ Mock database with loader schemas initialized");
  } catch (error) {
    console.error("❌ Mock database initialization failed:", error.message);
    throw error;
  }
}, 5000);

afterAll(async () => {
  // Clean up mock database
  try {
    if (db.closeDatabase) {
      await db.closeDatabase();
    }
    console.log("✅ Mock database cleanup completed");
  } catch (error) {
    console.error("❌ Error during mock database cleanup:", error);
  }
});
