#!/usr/bin/env node

const { query } = require('./utils/database');

process.env.NODE_ENV = "test";
process.env.DB_HOST = "localhost";
process.env.DB_USER = "postgres";
process.env.DB_PASSWORD = "password";
process.env.DB_NAME = "stocks";
process.env.DB_PORT = "5432";
process.env.DB_SSL = "false";

async function checkTables() {
  try {
    console.log("🔍 Checking for earnings-related tables...");

    const tablesQuery = `
      SELECT table_name
      FROM information_schema.tables
      WHERE table_schema = 'public'
      AND table_name LIKE '%earnings%'
      ORDER BY table_name
    `;

    const result = await query(tablesQuery);

    console.log("📊 Earnings-related tables found:");
    result.rows.forEach(row => {
      console.log(`  - ${row.table_name}`);
    });

    // Check analyst_estimates structure
    console.log("\n🔍 Checking analyst_estimates table structure:");
    const structureQuery = `
      SELECT column_name, data_type
      FROM information_schema.columns
      WHERE table_name = 'analyst_estimates'
      ORDER BY ordinal_position
    `;

    const structure = await query(structureQuery);
    structure.rows.forEach(row => {
      console.log(`  - ${row.column_name}: ${row.data_type}`);
    });

    console.log("\n✅ Table check complete!");
  } catch (error) {
    console.error("❌ Error checking tables:", error);
  }
  process.exit(0);
}

checkTables();