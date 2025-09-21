const { query } = require("./utils/database");

async function addMissingColumns() {
  try {
    console.log("🔧 Adding missing database columns...");

    // Add missing last_updated column to user_dashboard_settings
    await query(`
      ALTER TABLE user_dashboard_settings
      ADD COLUMN IF NOT EXISTS last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    `);
    console.log("✅ Added last_updated column to user_dashboard_settings");

    // Add any other missing columns identified from test failures
    await query(`
      ALTER TABLE user_dashboard_settings
      ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    `);
    console.log("✅ Added created_at column to user_dashboard_settings");

    console.log("🎯 Missing columns added successfully!");
  } catch (error) {
    console.error("❌ Error adding missing columns:", error);
    throw error;
  }
}

// Run the column additions
if (require.main === module) {
  addMissingColumns()
    .then(() => {
      console.log("✅ Database columns updated successfully");
    })
    .catch((error) => {
      console.error("❌ Failed to update database columns:", error);
      throw error;
    });
}

module.exports = { addMissingColumns };
