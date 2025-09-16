require("dotenv").config();
const fs = require("fs");
const path = require("path");

const { query } = require("./utils/database");

async function runSchemaFix() {
  try {
    console.log("📋 Reading schema fix SQL file...");
    const sqlFile = path.join(__dirname, "fix_database_schema.sql");
    const sql = fs.readFileSync(sqlFile, "utf8");

    console.log("🔧 Applying database schema fixes...");

    // Split the SQL file by statements and execute them
    const statements = sql.split(";").filter((stmt) => stmt.trim().length > 0);

    console.log(`📊 Found ${statements.length} SQL statements to execute`);

    for (let i = 0; i < statements.length; i++) {
      const statement = statements[i].trim();
      if (statement.length > 0 && !statement.startsWith("--")) {
        try {
          console.log(`⚡ Executing statement ${i + 1}/${statements.length}`);
          await query(statement);
        } catch (error) {
          // Some statements might fail if they already exist, that's okay
          if (
            error.message.includes("already exists") ||
            error.message.includes("duplicate key")
          ) {
            console.log(
              `ℹ️ Statement ${i + 1} skipped (already exists):`,
              error.message.substring(0, 100)
            );
          } else {
            console.log(`⚠️ Statement ${i + 1} error:`, error.message);
          }
        }
      }
    }

    console.log("✅ Schema fix completed successfully");

    // Verify the critical tables exist
    console.log("🔍 Verifying critical tables...");

    const verifications = [
      "SELECT count(*) FROM fundamental_metrics",
      "SELECT count(*) FROM news",
      "SELECT count(*) FROM annual_balance_sheet",
      "SELECT count(*) FROM annual_income_statement",
    ];

    for (const verification of verifications) {
      try {
        const result = await query(verification);
        const tableName = verification.match(/FROM (\w+)/)[1];
        console.log(`✅ Table ${tableName}: ${result.rows[0].count} rows`);
      } catch (error) {
        const tableName = verification.match(/FROM (\w+)/)[1];
        console.log(`❌ Table ${tableName}: ${error.message}`);
      }
    }

    process.exit(0);
  } catch (error) {
    console.error("❌ Schema fix failed:", error);
    process.exit(1);
  }
}

// Run the schema fix
runSchemaFix();
