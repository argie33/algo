const fs = require("fs");

const { query } = require("./utils/database");

async function applySchemaFix() {
  try {
    console.log("🔧 Applying database schema fixes...");

    const sqlScript = fs.readFileSync("./fix_schema_issues.sql", "utf8");
    const statements = sqlScript
      .split(";")
      .filter((stmt) => stmt.trim().length > 0);

    for (const statement of statements) {
      if (statement.trim()) {
        console.log(`Executing: ${statement.trim().substring(0, 50)}...`);
        await query(statement.trim());
      }
    }

    console.log("✅ Schema fixes applied successfully");

    // Test the fixes
    console.log("🧪 Testing dividend calendar query...");
    const _dividendTest = await query(`
      SELECT symbol, company_name, ex_dividend_date, payment_date, dividend_yield 
      FROM dividend_calendar 
      LIMIT 1
    `);
    console.log("✅ Dividend calendar test passed");

    console.log("🧪 Testing balance sheet query...");
    const balanceTest = await query(`
      SELECT symbol, date, item_name, value
      FROM annual_balance_sheet 
      WHERE symbol = 'AAPL' 
      LIMIT 3
    `);
    console.log(
      "✅ Balance sheet test passed:",
      balanceTest.rows.length,
      "rows found"
    );

    throw new Error("Script completed successfully");
  } catch (error) {
    console.error("❌ Schema fix failed:", error.message);
    throw error;
  }
}

applySchemaFix();
