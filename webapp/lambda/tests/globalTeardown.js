// Global teardown - runs once after all tests

module.exports = async () => {
  // Clean up any global resources

  try {
    // Ensure database connections are properly closed
    const db = require("../utils/database");
    if (db.closeDatabase) {
      await db.closeDatabase();
      console.log("🔌 Database connections closed in global teardown");
    }

    // Give time for connections to fully close
    await new Promise((resolve) => setTimeout(resolve, 1000));
  } catch (error) {
    console.error("❌ Error in global teardown:", error.message);
  }

  // Force garbage collection if available
  if (global.gc) {
    global.gc();
  }

  console.log("🧹 Global test teardown completed");
};
