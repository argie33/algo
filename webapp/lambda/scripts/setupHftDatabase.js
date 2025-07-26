#!/usr/bin/env node

/**
 * HFT Database Setup Script
 * Sets up HFT database tables and runs basic validation
 */

const fs = require('fs');
const path = require('path');
const { Client } = require('pg');

const config = {
  host: process.env.DB_HOST || 'localhost',
  port: process.env.DB_PORT || 5432,
  database: process.env.DB_NAME || 'financial_webapp',
  user: process.env.DB_USER || 'postgres',
  password: process.env.DB_PASSWORD || 'password'
};

async function setupHftDatabase() {
  console.log('🚀 Setting up HFT Database...\n');
  
  const client = new Client(config);
  
  try {
    // Connect to database
    console.log('📝 Connecting to database...');
    await client.connect();
    console.log('✅ Connected to database successfully\n');
    
    // Check if users table exists (prerequisite)
    console.log('🔍 Checking prerequisites...');
    const usersCheck = await client.query(`
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name = 'users'
      );
    `);
    
    if (!usersCheck.rows[0].exists) {
      console.log('❌ Users table not found. Please run the main database setup first.');
      process.exit(1);
    }
    console.log('✅ Prerequisites check passed\n');
    
    // Read and execute HFT schema
    console.log('📋 Loading HFT database schema...');
    const schemaPath = path.join(__dirname, '..', 'sql', 'hft_database_schema.sql');
    
    if (!fs.existsSync(schemaPath)) {
      console.log('❌ HFT schema file not found at:', schemaPath);
      process.exit(1);
    }
    
    const schemaSql = fs.readFileSync(schemaPath, 'utf8');
    console.log('✅ Schema loaded successfully\n');
    
    // Execute schema
    console.log('⚙️  Executing HFT database schema...');
    await client.query(schemaSql);
    console.log('✅ HFT database schema executed successfully\n');
    
    // Verify tables were created
    console.log('🔍 Verifying HFT tables...');
    const tablesCheck = await client.query(`
      SELECT table_name 
      FROM information_schema.tables 
      WHERE table_schema = 'public' AND table_name LIKE 'hft_%'
      ORDER BY table_name;
    `);
    
    const expectedTables = [
      'hft_strategies',
      'hft_positions', 
      'hft_orders',
      'hft_performance_metrics',
      'hft_risk_events',
      'hft_market_data'
    ];
    
    const createdTables = tablesCheck.rows.map(row => row.table_name);
    console.log('📊 Created tables:', createdTables.join(', '));
    
    const missingTables = expectedTables.filter(table => !createdTables.includes(table));
    if (missingTables.length > 0) {
      console.log('❌ Missing tables:', missingTables.join(', '));
      process.exit(1);
    }
    console.log('✅ All HFT tables created successfully\n');
    
    // Check indexes
    console.log('🔍 Verifying indexes...');
    const indexCheck = await client.query(`
      SELECT indexname 
      FROM pg_indexes 
      WHERE tablename LIKE 'hft_%' AND schemaname = 'public'
      ORDER BY indexname;
    `);
    
    console.log('📊 Created indexes:', indexCheck.rows.length);
    console.log('✅ Indexes verified\n');
    
    // Check views
    console.log('🔍 Verifying views...');
    const viewCheck = await client.query(`
      SELECT table_name 
      FROM information_schema.views 
      WHERE table_schema = 'public' AND table_name LIKE 'hft_%'
      ORDER BY table_name;
    `);
    
    const createdViews = viewCheck.rows.map(row => row.table_name);
    console.log('📊 Created views:', createdViews.join(', '));
    console.log('✅ Views verified\n');
    
    // Insert sample data for testing (optional)
    if (process.argv.includes('--sample-data')) {
      console.log('📝 Inserting sample data...');
      await insertSampleData(client);
      console.log('✅ Sample data inserted\n');
    }
    
    // Run validation tests
    console.log('🧪 Running validation tests...');
    await runValidationTests(client);
    console.log('✅ Validation tests passed\n');
    
    console.log('🎉 HFT Database setup completed successfully!');
    console.log('\n📈 Next steps:');
    console.log('1. Configure API keys in user_api_keys table');
    console.log('2. Create HFT strategies via API endpoints');
    console.log('3. Start HFT services for live trading');
    
  } catch (error) {
    console.error('❌ Error setting up HFT database:', error.message);
    if (error.code) {
      console.error('Error code:', error.code);
    }
    process.exit(1);
  } finally {
    await client.end();
  }
}

async function insertSampleData(client) {
  // Create a test user if it doesn't exist
  await client.query(`
    INSERT INTO users (id, email, password_hash, created_at)
    VALUES ('test-hft-user', 'hft-test@example.com', 'hashed-password', CURRENT_TIMESTAMP)
    ON CONFLICT (id) DO NOTHING;
  `);
  
  // Insert sample HFT strategy
  await client.query(`
    INSERT INTO hft_strategies (
      user_id, name, type, symbols, parameters, risk_parameters, 
      enabled, paper_trading, max_position_size, max_daily_loss
    ) VALUES (
      'test-hft-user',
      'Sample BTC Scalping Strategy',
      'scalping',
      ARRAY['BTC/USD', 'ETH/USD'],
      '{"minSpread": 0.001, "maxSpread": 0.005, "volumeThreshold": 1000, "momentumPeriod": 5, "executionDelay": 100}',
      '{"positionSize": 0.1, "stopLoss": 0.02, "takeProfit": 0.01, "maxDailyLoss": 500}',
      false,
      true,
      1000.00,
      500.00
    ) ON CONFLICT DO NOTHING;
  `);
  
  console.log('  • Sample user and strategy created');
}

async function runValidationTests(client) {
  const tests = [
    {
      name: 'Table Structure',
      query: `
        SELECT COUNT(*) as count 
        FROM information_schema.columns 
        WHERE table_name LIKE 'hft_%' AND table_schema = 'public';
      `,
      validate: (result) => parseInt(result.rows[0].count) > 40
    },
    {
      name: 'Foreign Key Constraints',
      query: `
        SELECT COUNT(*) as count
        FROM information_schema.table_constraints
        WHERE constraint_type = 'FOREIGN KEY' 
        AND table_name LIKE 'hft_%' 
        AND table_schema = 'public';
      `,
      validate: (result) => parseInt(result.rows[0].count) >= 5
    },
    {
      name: 'Check Constraints',
      query: `
        SELECT COUNT(*) as count
        FROM information_schema.table_constraints
        WHERE constraint_type = 'CHECK' 
        AND table_name LIKE 'hft_%' 
        AND table_schema = 'public';
      `,
      validate: (result) => parseInt(result.rows[0].count) >= 10
    },
    {
      name: 'Indexes',
      query: `
        SELECT COUNT(*) as count
        FROM pg_indexes
        WHERE tablename LIKE 'hft_%' AND schemaname = 'public';
      `,
      validate: (result) => parseInt(result.rows[0].count) >= 15
    },
    {
      name: 'Views',
      query: `
        SELECT COUNT(*) as count
        FROM information_schema.views
        WHERE table_name LIKE 'hft_%' AND table_schema = 'public';
      `,
      validate: (result) => parseInt(result.rows[0].count) >= 2
    }
  ];
  
  for (const test of tests) {
    try {
      const result = await client.query(test.query);
      const passed = test.validate(result);
      
      if (passed) {
        console.log(`  ✅ ${test.name}: PASSED`);
      } else {
        console.log(`  ❌ ${test.name}: FAILED`);
        console.log(`     Result: ${JSON.stringify(result.rows[0])}`);
        throw new Error(`Validation test failed: ${test.name}`);
      }
    } catch (error) {
      console.log(`  ❌ ${test.name}: ERROR - ${error.message}`);
      throw error;
    }
  }
}

// Run the setup if called directly
if (require.main === module) {
  setupHftDatabase().catch(error => {
    console.error('Setup failed:', error);
    process.exit(1);
  });
}

module.exports = { setupHftDatabase };