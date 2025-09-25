#!/usr/bin/env node

// Script to execute SQL fixes using the application's database connection
const fs = require('fs');
const path = require('path');

// Set up environment variables
process.env.NODE_ENV = "test";
process.env.DB_HOST = "localhost";
process.env.DB_USER = "postgres";
process.env.DB_PASSWORD = "password";
process.env.DB_NAME = "stocks";
process.env.DB_PORT = "5432";
process.env.DB_SSL = "false";

async function executeSqlFile(sqlFilePath) {
  const { query } = require('./utils/database');

  try {
    console.log(`📋 Reading SQL file: ${sqlFilePath}`);
    const sqlContent = fs.readFileSync(sqlFilePath, 'utf8');

    console.log(`🚀 Executing SQL content...`);
    await query(sqlContent);

    console.log(`✅ Successfully executed SQL file: ${sqlFilePath}`);
  } catch (error) {
    console.error(`❌ Error executing SQL file ${sqlFilePath}:`, error);
    throw error;
  }
}

async function main() {
  try {
    // Execute the analyst test data addition
    await executeSqlFile('./add_analyst_test_data.sql');

    console.log('🎉 Analyst test data added successfully!');
  } catch (error) {
    console.error('💥 SQL fix failed:', error);
    process.exit(1);
  }
}

main();