// Jest setup file

// Mock database connection for tests
const { initializeDatabase, closeDatabase } = require("./utils/database");

// Initialize database for tests
initializeDatabase().then(() => {
}).catch((err) => {
  console.error(" Failed to initialize database:", err.message);
});

// Cleanup after all tests
afterAll(async () => {
  await closeDatabase();
});
