
require("dotenv").config();
const { Pool } = require("pg");

async function checkDatabaseSchema() {
  const pool = new Pool({
    host: process.env.DB_HOST,
    user: process.env.DB_USER,
    password: process.env.DB_PASSWORD,
    database: process.env.DB_NAME,
    port: process.env.DB_PORT,
  });

  try {
    console.log("🔍 CHECKING DATABASE SCHEMA");
    console.log("===========================");

    // Check what tables exist
    const tablesResult = await pool.query(`
      SELECT table_name
      FROM information_schema.tables
      WHERE table_schema = 'public'
      ORDER BY table_name
    `);

    console.log("\n📊 Available Tables:");
    tablesResult.rows.forEach(row => {
      console.log(`- ${row.table_name}`);
    });

    // Check columns for key tables used in failing endpoints
    const keyTables = ['price_daily', 'company_profile', 'earnings_history', 'fundamental_metrics', 'technical_data_daily', 'market_data', 'buy_sell_daily'];

    for (const tableName of keyTables) {
      const tableExists = tablesResult.rows.some(row => row.table_name === tableName);
      if (tableExists) {
        console.log(`\n📋 Columns in ${tableName}:`);
        const columnsResult = await pool.query(`
          SELECT column_name, data_type, is_nullable
          FROM information_schema.columns
          WHERE table_name = $1
          ORDER BY column_name
        `, [tableName]);

        columnsResult.rows.forEach(row => {
          console.log(`  - ${row.column_name} (${row.data_type}${row.is_nullable === 'YES' ? ', nullable' : ''})`);
        });
      } else {
        console.log(`\n❌ Table ${tableName} does not exist`);
      }
    }

    console.log("\n✅ Schema check completed");
  } catch (error) {
    console.error("❌ Error:", error.message);
  } finally {
    await pool.end();
  }
}

checkDatabaseSchema();
