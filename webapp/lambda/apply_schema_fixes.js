const fs = require("fs");
const path = require("path");

const { query } = require("./utils/database");

async function applySchemaFixes() {
  try {
    console.log("🔧 Applying comprehensive database schema fixes...");

    const sqlContent = fs.readFileSync(
      path.join(__dirname, "fix_database_schema_complete.sql"),
      "utf8"
    );

    // Split SQL content by statements, excluding empty lines and comments
    const statements = sqlContent
      .split(";")
      .map((stmt) => stmt.trim())
      .filter(
        (stmt) =>
          stmt &&
          !stmt.startsWith("--") &&
          stmt !== "BEGIN" &&
          stmt !== "COMMIT"
      );

    let successCount = 0;
    let failureCount = 0;

    for (const statement of statements) {
      if (!statement) continue;

      try {
        await query(statement);
        successCount++;
        console.log(`✅ Statement executed successfully`);
      } catch (error) {
        failureCount++;
        console.log(`❌ Statement failed: ${error.message}`);
        console.log(`Statement: ${statement.substring(0, 100)}...`);
      }
    }

    console.log(`\n📊 Schema fix results:`);
    console.log(`✅ Successful: ${successCount}`);
    console.log(`❌ Failed: ${failureCount}`);

    // Verify some key fixes
    console.log("\n🔍 Verifying key schema changes...");

    try {
      const result = await query(`
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name IN ('stock_scores', 'market_indices', 'portfolio_risk', 'price_daily')
        AND column_name IN ('sentiment', 'change_amount', 'var_1d', 'previous_close')
        ORDER BY table_name, column_name
      `);

      console.log("Added columns verification:");
      result.rows.forEach((row) => {
        console.log(`  ✅ ${row.column_name} (${row.data_type})`);
      });
    } catch (error) {
      console.log(`❌ Verification failed: ${error.message}`);
    }

    // Check if new tables exist
    try {
      const tableCheck = await query(`
        SELECT table_name
        FROM information_schema.tables
        WHERE table_name IN ('annual_balance_sheet', 'annual_income_statement')
        AND table_schema = 'public'
      `);

      console.log("\nNew tables verification:");
      tableCheck.rows.forEach((row) => {
        console.log(`  ✅ ${row.table_name} table created`);
      });
    } catch (error) {
      console.log(`❌ Table verification failed: ${error.message}`);
    }

    console.log("\n🎯 Database schema fixes completed!");
  } catch (error) {
    console.error("❌ Critical error applying schema fixes:", error);
    throw error;
  }
}

// Run the schema fixes
if (require.main === module) {
  applySchemaFixes()
    .then(() => {
      console.log("✅ Schema fixes applied successfully");
    })
    .catch((error) => {
      console.error("❌ Failed to apply schema fixes:", error);
      throw error;
    });
}

module.exports = { applySchemaFixes };
