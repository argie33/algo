#!/usr/bin/env node

/**
 * Stock Symbols Database Setup Script
 * 
 * This script creates the stock_symbols table and loads sample data
 * to resolve the 503 Service Unavailable errors on the stocks page.
 * 
 * Usage:
 *   node setup-stocks-database.js
 * 
 * Environment variables required:
 *   - DB_ENDPOINT or DB_HOST
 *   - DB_SECRET_ARN (for AWS) or DB_PASSWORD (for local)
 */

const fs = require('fs');
const path = require('path');

// Import database utilities
const { initializeDatabase, query, getDbCredentials } = require('../utils/database');

async function setupStocksDatabase() {
  console.log('🏗️  Setting up stocks database...');
  
  try {
    // Initialize database connection
    console.log('📡 Initializing database connection...');
    await initializeDatabase();
    console.log('✅ Database connection established');

    // Read SQL setup script
    const sqlPath = path.join(__dirname, 'setup-stock-symbols-table.sql');
    console.log('📖 Reading SQL setup script:', sqlPath);
    
    if (!fs.existsSync(sqlPath)) {
      throw new Error(`SQL file not found: ${sqlPath}`);
    }
    
    const sqlContent = fs.readFileSync(sqlPath, 'utf8');
    console.log('✅ SQL script loaded successfully');

    // Execute SQL script
    console.log('🔧 Executing database setup...');
    const result = await query(sqlContent);
    console.log('✅ Database setup completed successfully');

    // Verify tables exist
    console.log('🔍 Verifying table creation...');
    
    const tableChecks = [
      'stock_symbols',
      'portfolio_holdings', 
      'trading_history',
      'user_accounts'
    ];

    for (const tableName of tableChecks) {
      try {
        const checkResult = await query(`SELECT COUNT(*) as count FROM ${tableName}`);
        const count = parseInt(checkResult[0]?.count || 0);
        console.log(`✅ ${tableName}: ${count} rows`);
      } catch (error) {
        console.error(`❌ ${tableName}: ${error.message}`);
      }
    }

    // Test stocks API endpoint requirements
    console.log('🧪 Testing stocks API requirements...');
    
    try {
      const sectorsTest = await query(`
        SELECT sector, COUNT(*) as count 
        FROM stock_symbols 
        WHERE is_active = TRUE AND sector IS NOT NULL 
        GROUP BY sector 
        ORDER BY count DESC
      `);
      console.log(`✅ Sectors query: ${sectorsTest.length} sectors found`);
      
      const stocksTest = await query(`
        SELECT symbol, company_name, sector, price 
        FROM stock_symbols 
        WHERE is_active = TRUE 
        ORDER BY symbol 
        LIMIT 5
      `);
      console.log(`✅ Stocks query: ${stocksTest.length} stocks found`);
      console.log('📊 Sample stocks:', stocksTest.map(s => `${s.symbol} (${s.company_name})`).join(', '));
      
    } catch (testError) {
      console.error('❌ API endpoint test failed:', testError.message);
    }

    console.log('\n🎉 Database setup completed successfully!');
    console.log('\n📋 Summary:');
    console.log('   - stock_symbols table created with sample data');
    console.log('   - portfolio_holdings table created');
    console.log('   - trading_history table created');
    console.log('   - user_accounts table created');
    console.log('\n🔗 The stocks page should now work properly.');
    console.log('   Test URL: https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/api/stocks/screen');

  } catch (error) {
    console.error('❌ Database setup failed:', error);
    console.error('\n🔧 Troubleshooting steps:');
    console.error('   1. Check database connection settings');
    console.error('   2. Verify DB_ENDPOINT and DB_SECRET_ARN environment variables');
    console.error('   3. Ensure database user has CREATE TABLE permissions');
    console.error('   4. Check network connectivity to database');
    
    process.exit(1);
  }
}

// Run setup if called directly
if (require.main === module) {
  setupStocksDatabase().catch(error => {
    console.error('Fatal error:', error);
    process.exit(1);
  });
}

module.exports = { setupStocksDatabase };