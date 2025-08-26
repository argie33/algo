#!/usr/bin/env node

/**
 * Demo Portfolio Data Population Script
 * 
 * This script creates realistic portfolio data for testing and demonstration.
 * It creates multiple demo users with different portfolio styles:
 * - Conservative investor (bonds, dividend stocks, blue chips)
 * - Growth investor (tech stocks, growth companies)
 * - Value investor (undervalued stocks, value plays)
 * - Balanced investor (mix of growth and value)
 * 
 * Usage: node populate-demo-portfolios.js
 */

const { Pool } = require('pg');

// Database configuration for ECS task environment
const getDatabaseConfig = () => {
  if (process.env.DB_HOST) {
    return {
      host: process.env.DB_HOST,
      port: process.env.DB_PORT || 5432,
      database: process.env.DB_NAME || 'stocks',
      user: process.env.DB_USER || 'postgres',
      password: process.env.DB_PASSWORD,
      ssl: process.env.DB_SSL === 'true'
    };
  }
  
  // Fallback for local development
  return {
    host: 'localhost',
    port: 5432,
    database: 'stocks',
    user: 'postgres',
    password: 'password',
    ssl: false
  };
};

// Demo portfolio configurations
const DEMO_PORTFOLIOS = {
  'demo-conservative-investor': {
    name: 'Conservative Investor',
    style: 'Conservative',
    riskTolerance: 'low',
    positions: [
      { symbol: 'AAPL', quantity: 50, avgCost: 175.00, sector: 'Technology' },
      { symbol: 'MSFT', quantity: 40, avgCost: 300.00, sector: 'Technology' },
      { symbol: 'JNJ', quantity: 60, avgCost: 160.00, sector: 'Healthcare' },
      { symbol: 'PG', quantity: 45, avgCost: 140.00, sector: 'Consumer Goods' },
      { symbol: 'KO', quantity: 80, avgCost: 55.00, sector: 'Consumer Goods' },
      { symbol: 'VTI', quantity: 100, avgCost: 220.00, sector: 'ETF' },
      { symbol: 'BND', quantity: 200, avgCost: 80.00, sector: 'Bonds' },
    ]
  },
  
  'demo-growth-investor': {
    name: 'Growth Investor', 
    style: 'Growth',
    riskTolerance: 'high',
    positions: [
      { symbol: 'TSLA', quantity: 30, avgCost: 250.00, sector: 'Automotive' },
      { symbol: 'NVDA', quantity: 25, avgCost: 400.00, sector: 'Technology' },
      { symbol: 'AMZN', quantity: 15, avgCost: 3200.00, sector: 'Technology' },
      { symbol: 'GOOGL', quantity: 10, avgCost: 2800.00, sector: 'Technology' },
      { symbol: 'META', quantity: 20, avgCost: 280.00, sector: 'Technology' },
      { symbol: 'NFLX', quantity: 25, avgCost: 420.00, sector: 'Media' },
      { symbol: 'ROKU', quantity: 50, avgCost: 120.00, sector: 'Media' },
    ]
  },
  
  'demo-value-investor': {
    name: 'Value Investor',
    style: 'Value', 
    riskTolerance: 'medium',
    positions: [
      { symbol: 'BRK.B', quantity: 40, avgCost: 320.00, sector: 'Financial' },
      { symbol: 'JPM', quantity: 35, avgCost: 140.00, sector: 'Financial' },
      { symbol: 'WMT', quantity: 60, avgCost: 145.00, sector: 'Retail' },
      { symbol: 'HD', quantity: 30, avgCost: 280.00, sector: 'Retail' },
      { symbol: 'XOM', quantity: 80, avgCost: 85.00, sector: 'Energy' },
      { symbol: 'CVX', quantity: 45, avgCost: 155.00, sector: 'Energy' },
      { symbol: 'T', quantity: 120, avgCost: 18.00, sector: 'Telecommunications' },
    ]
  },
  
  'demo-balanced-investor': {
    name: 'Balanced Investor',
    style: 'Balanced',
    riskTolerance: 'medium', 
    positions: [
      { symbol: 'SPY', quantity: 100, avgCost: 420.00, sector: 'ETF' },
      { symbol: 'QQQ', quantity: 50, avgCost: 350.00, sector: 'ETF' },
      { symbol: 'AAPL', quantity: 40, avgCost: 175.00, sector: 'Technology' },
      { symbol: 'MSFT', quantity: 35, avgCost: 300.00, sector: 'Technology' },
      { symbol: 'AMZN', quantity: 8, avgCost: 3200.00, sector: 'Technology' },
      { symbol: 'TSLA', quantity: 15, avgCost: 250.00, sector: 'Automotive' },
      { symbol: 'JNJ', quantity: 30, avgCost: 160.00, sector: 'Healthcare' },
      { symbol: 'JPM', quantity: 25, avgCost: 140.00, sector: 'Financial' },
    ]
  }
};

async function populateDemoPortfolios() {
  const config = getDatabaseConfig();
  const pool = new Pool(config);
  
  console.log('🎯 Starting Demo Portfolio Population');
  console.log('====================================');
  console.log(`📊 Database: ${config.host}:${config.port}/${config.database}`);
  console.log(`👥 Creating ${Object.keys(DEMO_PORTFOLIOS).length} demo portfolios...`);

  try {
    // Test database connection
    const client = await pool.connect();
    console.log('✅ Database connection established');

    // Clear existing demo data
    console.log('\n🧹 Clearing existing demo portfolio data...');
    await client.query(`
      DELETE FROM user_portfolio 
      WHERE user_id LIKE 'demo-%'
    `);
    console.log('   Cleared existing demo portfolios');

    // Insert demo portfolios
    let totalPositions = 0;
    for (const [userId, portfolio] of Object.entries(DEMO_PORTFOLIOS)) {
      console.log(`\n👤 Creating portfolio for: ${portfolio.name} (${userId})`);
      console.log(`   Style: ${portfolio.style} | Risk: ${portfolio.riskTolerance}`);
      console.log(`   Positions: ${portfolio.positions.length}`);
      
      for (const position of portfolio.positions) {
        await client.query(`
          INSERT INTO user_portfolio (user_id, symbol, quantity, avg_cost, last_updated)
          VALUES ($1, $2, $3, $4, NOW())
          ON CONFLICT (user_id, symbol) 
          DO UPDATE SET 
            quantity = EXCLUDED.quantity,
            avg_cost = EXCLUDED.avg_cost,
            last_updated = EXCLUDED.last_updated
        `, [userId, position.symbol, position.quantity, position.avgCost]);
        
        totalPositions++;
      }
      
      // Calculate total portfolio value for logging
      const totalValue = portfolio.positions.reduce((sum, pos) => {
        return sum + (pos.quantity * pos.avgCost);
      }, 0);
      
      console.log(`   Portfolio Value: $${totalValue.toLocaleString()}`);
      console.log(`   Largest Holding: ${portfolio.positions[0].symbol} (${portfolio.positions[0].quantity} shares)`);
    }

    // Verify data insertion
    console.log('\n📊 Verifying portfolio data...');
    const verification = await client.query(`
      SELECT 
        user_id,
        COUNT(*) as positions,
        SUM(quantity * avg_cost) as total_value
      FROM user_portfolio 
      WHERE user_id LIKE 'demo-%'
      GROUP BY user_id
      ORDER BY total_value DESC
    `);

    console.log('\n✅ Demo Portfolios Created Successfully!');
    console.log('========================================');
    
    verification.rows.forEach(row => {
      const portfolio = DEMO_PORTFOLIOS[row.user_id];
      console.log(`📊 ${portfolio?.name || row.user_id}:`);
      console.log(`   Positions: ${row.positions}`);
      console.log(`   Total Value: $${parseFloat(row.total_value).toLocaleString()}`);
    });

    console.log(`\n🎯 Summary:`);
    console.log(`   Demo Users: ${verification.rows.length}`);
    console.log(`   Total Positions: ${totalPositions}`);
    console.log(`   Combined Portfolio Value: $${verification.rows.reduce((sum, row) => sum + parseFloat(row.total_value), 0).toLocaleString()}`);

    console.log('\n🔗 Testing Portfolio API Access:');
    console.log('   API Endpoint: /api/portfolio/analytics');
    console.log('   Demo User IDs:');
    verification.rows.forEach(row => {
      console.log(`     - ${row.user_id}`);
    });

    console.log('\n💡 Next Steps:');
    console.log('1. Test authenticated API calls with demo user IDs');
    console.log('2. Validate portfolio analytics calculations');
    console.log('3. Test frontend portfolio visualization');
    console.log('4. Implement user registration flow for real portfolios');

    client.release();
    
  } catch (error) {
    console.error('❌ Failed to populate demo portfolios:', error.message);
    console.error('   Details:', error);
    throw error;
  } finally {
    await pool.end();
  }
}

// Run the population script
if (require.main === module) {
  populateDemoPortfolios()
    .then(() => {
      console.log('\n✅ Demo portfolio population completed successfully!');
      process.exit(0);
    })
    .catch((error) => {
      console.error('\n❌ Demo portfolio population failed:', error.message);
      process.exit(1);
    });
}

module.exports = { populateDemoPortfolios, DEMO_PORTFOLIOS };