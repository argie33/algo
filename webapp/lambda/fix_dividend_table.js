const { query } = require("./utils/database");

async function fixDividendTable() {
  try {
    console.log("🔧 Fixing dividend_calendar table schema...");

    // Add missing columns if they don't exist
    await query(`
      ALTER TABLE dividend_calendar 
      ADD COLUMN IF NOT EXISTS ex_dividend_date DATE,
      ADD COLUMN IF NOT EXISTS payment_date DATE,
      ADD COLUMN IF NOT EXISTS dividend_yield DECIMAL(6,3),
      ADD COLUMN IF NOT EXISTS announcement_date DATE;
    `);

    console.log("✅ Added new columns");

    // Copy data from old columns to new columns
    await query(`
      UPDATE dividend_calendar 
      SET 
        ex_dividend_date = COALESCE(ex_dividend_date, ex_date),
        payment_date = COALESCE(payment_date, pay_date),
        dividend_yield = COALESCE(dividend_yield, yield_percent)
      WHERE ex_dividend_date IS NULL OR payment_date IS NULL OR dividend_yield IS NULL;
    `);

    console.log("✅ Migrated data from old columns");

    // Test the new schema
    const testResult = await query(`
      SELECT symbol, ex_dividend_date, payment_date, dividend_yield
      FROM dividend_calendar 
      LIMIT 1
    `);

    console.log("✅ Schema fix completed successfully");
    console.log("Test query result:", testResult.rows);

    throw new Error("Script completed successfully");
  } catch (error) {
    console.error("❌ Failed to fix dividend table:", error.message);
    console.error("Error details:", error);
    throw error;
  }
}

fixDividendTable();
