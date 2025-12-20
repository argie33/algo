// Jest setup file
console.log("🔧 Jest setup file loaded");

// Mock database connection for tests
const { initializeDatabase, closeDatabase } = require("./utils/database");

// Initialize database for tests
console.log("🔧 Initializing database connection pool...");
initializeDatabase().then(() => {
  console.log("✅ Database connection pool initialized successfully");
}).catch((err) => {
  console.error("❌ Failed to initialize database:", err.message);
});

// Cleanup after all tests
afterAll(async () => {
  console.log("🔧 Closing database connection pool...");
  await closeDatabase();
  console.log("✅ Database connection pool closed");
});
