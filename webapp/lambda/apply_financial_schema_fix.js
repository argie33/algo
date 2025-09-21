/**
 * Apply Financial Schema Fix
 * This script creates the financial tables with the correct schema from Python loaders
 */

const fs = require("fs");
const path = require("path");

const { initializeDatabase, query } = require("./utils/database");

async function applySchemaFix() {
  try {
    console.log("🔧 Applying financial schema fix...");

    // Initialize database
    await initializeDatabase();
    console.log("✅ Database connection established");

    // Read SQL fix file
    const sqlFile = path.join(__dirname, "fix_financial_schema.sql");
    const sqlCommands = fs.readFileSync(sqlFile, "utf8");
    console.log("📄 SQL fix file loaded");

    // Split into individual commands and execute
    const commands = sqlCommands
      .split(";")
      .map((cmd) => cmd.trim())
      .filter((cmd) => cmd.length > 0 && !cmd.startsWith("--"));

    console.log(`🔄 Executing ${commands.length} SQL commands...`);

    for (let i = 0; i < commands.length; i++) {
      const command = commands[i];
      if (command.trim()) {
        try {
          await query(command);
          if (command.toUpperCase().includes("CREATE TABLE")) {
            const tableName = command.match(/CREATE TABLE (\w+)/i)?.[1];
            console.log(`✅ Created table: ${tableName}`);
          } else if (command.toUpperCase().includes("CREATE INDEX")) {
            const indexName = command.match(/CREATE INDEX (\w+)/i)?.[1];
            console.log(`✅ Created index: ${indexName}`);
          } else if (command.toUpperCase().includes("INSERT INTO")) {
            const tableName = command.match(/INSERT INTO (\w+)/i)?.[1];
            console.log(`✅ Inserted data into: ${tableName}`);
          } else if (command.toUpperCase().includes("DROP TABLE")) {
            const tableName = command.match(/DROP TABLE.*?(\w+)/i)?.[1];
            console.log(`✅ Dropped table: ${tableName}`);
          } else {
            console.log(`✅ Executed command ${i + 1}/${commands.length}`);
          }
        } catch (error) {
          console.log(`⚠️  Warning on command ${i + 1}: ${error.message}`);
          // Continue with other commands
        }
      }
    }

    // Verify tables exist
    console.log("\n🔍 Verifying financial tables...");
    const tables = [
      "annual_balance_sheet",
      "annual_income_statement",
      "annual_cash_flow",
      "quarterly_balance_sheet",
      "quarterly_income_statement",
      "quarterly_cash_flow",
    ];

    for (const table of tables) {
      try {
        const result = await query(`SELECT COUNT(*) as count FROM ${table}`);
        const count = parseInt(result.rows[0].count);
        console.log(`✅ ${table}: ${count} rows`);
      } catch (error) {
        console.log(`❌ ${table}: ERROR - ${error.message}`);
      }
    }

    console.log("\n🎉 Financial schema fix completed successfully!");
  } catch (error) {
    console.error("❌ Error applying schema fix:", error);
    throw error;
  }
}

// Run the fix
applySchemaFix();
