// Jest setup file - runs before each test file

// Set test environment FIRST before any imports
process.env.NODE_ENV = "test";
process.env.ALLOW_DEV_BYPASS = "true";
process.env.JWT_SECRET = "test-secret-key-for-testing-only";

// Set database environment variables BEFORE importing any modules
process.env.DB_HOST = "localhost";
process.env.DB_USER = "postgres";
process.env.DB_PASSWORD = "password";
process.env.DB_NAME = "stocks";
process.env.DB_PORT = "5432";
process.env.DB_SSL = "false";
process.env.DB_CONNECT_TIMEOUT = "15000";
process.env.DB_POOL_IDLE_TIMEOUT = "30000";
process.env.DB_POOL_MAX = "5";

// Debug environment variables
console.log("🔧 Test setup - Environment variables:", {
  NODE_ENV: process.env.NODE_ENV,
  DB_HOST: process.env.DB_HOST,
  DB_USER: process.env.DB_USER,
  DB_NAME: process.env.DB_NAME,
  DB_PORT: process.env.DB_PORT,
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

// Initialize database for tests
const db = require("../utils/database");

// Mark database as available for all tests
global.DATABASE_AVAILABLE = () => true;
global.TEST_DB = db;

beforeAll(async () => {
  // Initialize real database connection for tests
  try {
    console.log("🔄 Initializing test database connection...");

    // Initialize database with shorter timeout for faster tests
    let timeoutId;
    const timeoutPromise = new Promise((_, reject) => {
      timeoutId = setTimeout(
        () => reject(new Error("Database initialization timeout")),
        8000
      );
    });

    const initPromise = db.initializeDatabase();
    const pool = await Promise.race([initPromise, timeoutPromise]);

    // Clear timeout if initialization succeeded
    if (timeoutId) {
      clearTimeout(timeoutId);
    }

    if (!pool) {
      throw new Error("Database pool initialization returned null");
    }

    // Quick connection test
    const queryTimeout = new Promise((_, reject) =>
      setTimeout(() => reject(new Error("Database query timeout")), 3000)
    );

    const queryPromise = db.query("SELECT 1 as test");
    const testResult = await Promise.race([queryPromise, queryTimeout]);

    if (!testResult || !testResult.rows || testResult.rows.length === 0) {
      throw new Error("Database query test failed - no results");
    }

    console.log("✅ Real PostgreSQL test database connected");
  } catch (error) {
    console.error("❌ Database connection failed for tests:", error.message);
    throw error; // Fail fast - no fallback mode, tests must use real database
  }
}, 15000);

afterAll(async () => {
  // Clean up database connection
  try {
    const db = require("../utils/database");
    if (db.closeDatabase) {
      await db.closeDatabase();
    }
    console.log("✅ Test database connection closed");
  } catch (error) {
    console.error("❌ Error closing test database:", error);
  }
});
