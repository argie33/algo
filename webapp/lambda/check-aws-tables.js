#!/usr/bin/env node
/**
 * Check what tables and columns exist on AWS RDS
 */

require("dotenv").config();
const { Pool } = require("pg");

// AWS RDS connection config
const pool = new Pool({
  host: process.env.DB_HOST,
  user: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  database: process.env.DB_NAME,
  port: process.env.DB_PORT,
  ssl: process.env.DB_SSL === 'true',
});

async function checkTables() {
  const client = await pool.connect();

  try {
    console.log("🔍 Checking AWS RDS database structure...");

    // Check what tables exist
    const tablesResult = await client.query(`
      SELECT table_name
      FROM information_schema.tables
      WHERE table_schema = 'public'
      ORDER BY table_name
    `);

    console.log("\n📊 Available tables:");
    tablesResult.rows.forEach(row => {
      console.log(`  - ${row.table_name}`);
    });

    // Check fundamental_metrics table structure if it exists
    if (tablesResult.rows.some(row => row.table_name === 'fundamental_metrics')) {
      console.log("\n🔍 fundamental_metrics table columns:");
      const columnsResult = await client.query(`
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'fundamental_metrics'
        ORDER BY ordinal_position
      `);

      columnsResult.rows.forEach(row => {
        console.log(`  - ${row.column_name} (${row.data_type})`);
      });
    }

    // Check other key tables
    const keyTables = ['stocks', 'price_daily', 'stock_symbols', 'portfolio_performance'];
    for (const tableName of keyTables) {
      if (tablesResult.rows.some(row => row.table_name === tableName)) {
        console.log(`\n🔍 ${tableName} table columns:`);
        const columnsResult = await client.query(`
          SELECT column_name, data_type
          FROM information_schema.columns
          WHERE table_name = $1
          ORDER BY ordinal_position
        `, [tableName]);

        columnsResult.rows.forEach(row => {
          console.log(`  - ${row.column_name} (${row.data_type})`);
        });
      }
    }

  } catch (error) {
    console.error("❌ Error checking tables:", error.message);
  } finally {
    client.release();
  }
}

async function main() {
  try {
    await checkTables();
  } catch (error) {
    console.error("💥 Check failed:", error.message);
    process.exit(1);
  } finally {
    await pool.end();
  }
}

if (require.main === module) {
  main();
}
