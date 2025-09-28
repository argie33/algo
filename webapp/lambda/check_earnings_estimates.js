
const { query } = require('./utils/database');

process.env.NODE_ENV = "test";
process.env.DB_HOST = "localhost";
process.env.DB_USER = "postgres";
process.env.DB_PASSWORD = "password";
process.env.DB_NAME = "stocks";
process.env.DB_PORT = "5432";
process.env.DB_SSL = "false";

async function checkEarningsEstimates() {
  try {
    console.log("🔍 Checking earnings_estimates table structure...");

    const structureQuery = `
      SELECT column_name, data_type
      FROM information_schema.columns
      WHERE table_name = 'earnings_estimates'
      ORDER BY ordinal_position
    `;

    const structure = await query(structureQuery);
    console.log("📊 earnings_estimates columns:");
    structure.rows.forEach(row => {
      console.log(`  - ${row.column_name}: ${row.data_type}`);
    });

    console.log("\n🔍 Sample data from earnings_estimates...");
    const sampleQuery = `
      SELECT * FROM earnings_estimates
      WHERE symbol IN ('AAPL', 'MSFT', 'GOOGL')
      LIMIT 5
    `;

    const sample = await query(sampleQuery);
    console.log("📊 Sample earnings_estimates data:");
    sample.rows.forEach((row, i) => {
      console.log(`  Record ${i+1}:`, JSON.stringify(row, null, 2));
    });

    console.log("\n✅ earnings_estimates check complete!");
  } catch (error) {
    console.error("❌ Error checking earnings_estimates:", error);
  }
  process.exit(0);
}

checkEarningsEstimates();