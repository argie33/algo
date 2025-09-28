
const { query } = require('./utils/database');

process.env.NODE_ENV = "test";
process.env.DB_HOST = "localhost";
process.env.DB_USER = "postgres";
process.env.DB_PASSWORD = "password";
process.env.DB_NAME = "stocks";
process.env.DB_PORT = "5432";
process.env.DB_SSL = "false";

async function checkETFTables() {
  try {
    console.log("🔍 Checking ETF-related tables...");

    const tablesQuery = `
      SELECT table_name
      FROM information_schema.tables
      WHERE table_schema = 'public'
      AND table_name LIKE '%etf%'
      ORDER BY table_name
    `;

    const result = await query(tablesQuery);

    console.log("📊 ETF-related tables found:");
    result.rows.forEach(row => {
      console.log(`  - ${row.table_name}`);
    });

    // Also check for price_daily table
    console.log("\n🔍 Checking for price_daily table:");
    const priceTableQuery = `
      SELECT table_name
      FROM information_schema.tables
      WHERE table_schema = 'public'
      AND table_name = 'price_daily'
    `;

    const priceResult = await query(priceTableQuery);
    if (priceResult.rows.length > 0) {
      console.log("✅ price_daily table exists");
    } else {
      console.log("❌ price_daily table not found");
    }

    console.log("\n✅ Table check complete!");
  } catch (error) {
    console.error("❌ Error checking tables:", error);
  }
  process.exit(0);
}

checkETFTables();