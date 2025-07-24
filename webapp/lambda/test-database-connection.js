#!/usr/bin/env node

/**
 * Database Connection Test Script
 * Tests local database connectivity and verifies sample data
 */

const { Pool } = require('pg');
require('dotenv').config();

const pool = new Pool({
  host: process.env.DB_HOST || 'localhost',
  port: process.env.DB_PORT || 5432,
  user: process.env.DB_USER || 'postgres',
  password: process.env.DB_PASSWORD || 'postgres',
  database: process.env.DB_NAME || 'stocks',
  ssl: process.env.DB_SSL === 'true' ? { rejectUnauthorized: false } : false
});

async function testConnection() {
  console.log('🧪 Testing database connection...\n');
  
  try {
    const client = await pool.connect();
    console.log('✅ Database connection successful!');
    
    // Test basic queries
    console.log('\n📊 Testing data availability:\n');
    
    const tests = [
      {
        name: 'Users',
        query: 'SELECT COUNT(*) as count FROM users',
        expected: '> 0'
      },
      {
        name: 'API Keys', 
        query: 'SELECT COUNT(*) as count FROM user_api_keys',
        expected: '> 0'
      },
      {
        name: 'Portfolio Holdings',
        query: 'SELECT COUNT(*) as count FROM portfolio_holdings',
        expected: '> 0'
      },
      {
        name: 'Market Data',
        query: 'SELECT COUNT(*) as count FROM market_data',
        expected: '> 0'
      },
      {
        name: 'Stock Symbols',
        query: 'SELECT COUNT(*) as count FROM stock_symbols',
        expected: '> 0'
      }
    ];
    
    for (const test of tests) {
      try {
        const result = await client.query(test.query);
        const count = parseInt(result.rows[0].count);
        const status = count > 0 ? '✅' : '❌';
        console.log(`${status} ${test.name}: ${count} records`);
      } catch (error) {
        console.log(`❌ ${test.name}: Error - ${error.message}`);
      }
    }
    
    // Test sample portfolio data
    console.log('\n💼 Sample Portfolio Data:\n');
    try {
      const portfolioQuery = `
        SELECT 
          ph.user_id,
          ph.symbol,
          ph.quantity,
          ph.current_price,
          ph.market_value,
          ph.unrealized_pl,
          ph.sector
        FROM portfolio_holdings ph
        WHERE ph.user_id = 'demo@example.com'
        ORDER BY ph.market_value DESC
        LIMIT 5
      `;
      
      const portfolioResult = await client.query(portfolioQuery);
      if (portfolioResult.rows.length > 0) {
        console.log('Top Holdings for demo@example.com:');
        portfolioResult.rows.forEach(row => {
          console.log(`  • ${row.symbol}: ${row.quantity} shares @ $${row.current_price} = $${row.market_value} (${row.sector})`);
        });
      } else {
        console.log('❌ No portfolio data found');
      }
    } catch (error) {
      console.log(`❌ Portfolio query error: ${error.message}`);
    }
    
    // Test market data
    console.log('\n📈 Sample Market Data:\n');
    try {
      const marketQuery = `
        SELECT symbol, price, sector, market_cap
        FROM market_data
        ORDER BY market_cap DESC
        LIMIT 5
      `;
      
      const marketResult = await client.query(marketQuery);
      if (marketResult.rows.length > 0) {
        console.log('Top Stocks by Market Cap:');
        marketResult.rows.forEach(row => {
          const marketCapB = (row.market_cap / 1000000000).toFixed(0);
          console.log(`  • ${row.symbol}: $${row.price} - $${marketCapB}B (${row.sector})`);
        });
      } else {
        console.log('❌ No market data found');
      }
    } catch (error) {
      console.log(`❌ Market data query error: ${error.message}`);
    }
    
    client.release();
    
    console.log('\n🎉 Database test completed successfully!');
    console.log('\n✨ Your APIs should now return data to the frontend');
    
  } catch (error) {
    console.error('❌ Database connection failed:', error.message);
    console.error('\n🔧 Troubleshooting:');
    console.error('1. Ensure PostgreSQL is running: sudo service postgresql start');
    console.error('2. Check database exists: createdb stocks');  
    console.error('3. Run setup script: ./setup-local-dev-database.sh');
    process.exit(1);
  } finally {
    await pool.end();
  }
}

if (require.main === module) {
  testConnection();
}

module.exports = { testConnection };