
const { query } = require('./utils/database');

process.env.NODE_ENV = "test";
process.env.DB_HOST = "localhost";
process.env.DB_USER = "postgres";
process.env.DB_PASSWORD = "password";
process.env.DB_NAME = "stocks";
process.env.DB_PORT = "5432";
process.env.DB_SSL = "false";

async function checkPriceDailySchema() {
  try {
    console.log("🔍 Checking price_daily table schema...");

    const schemaQuery = `
      SELECT column_name, data_type, is_nullable
      FROM information_schema.columns
      WHERE table_name = 'price_daily'
      ORDER BY ordinal_position
    `;

    const result = await query(schemaQuery);

    console.log("📊 price_daily table columns:");
    result.rows.forEach(row => {
      console.log(`  - ${row.column_name}: ${row.data_type} (${row.is_nullable === 'YES' ? 'nullable' : 'not null'})`);
    });

    console.log("\n✅ Schema check complete!");
  } catch (error) {
    console.error("❌ Error checking schema:", error);
  }
  process.exit(0);
}

checkPriceDailySchema();