#!/usr/bin/env node

/**
 * Setup Economic Database Schema and Initial Data
 * Initializes the economic database tables and populates with seed data
 */

const fs = require('fs');
const path = require('path');

// Import database utilities
let query, initializeDatabase;
try {
  const dbUtils = require('../utils/database');
  ({ query, initializeDatabase } = dbUtils);
} catch (error) {
  console.error('❌ Database utilities not available:', error.message);
  process.exit(1);
}

async function setupEconomicDatabase() {
  console.log('🚀 Setting up Economic Database Schema...');
  
  try {
    // Initialize database connection
    console.log('📡 Initializing database connection...');
    await initializeDatabase();
    console.log('✅ Database connection established');
    
    // Read the schema SQL file
    const schemaPath = path.join(__dirname, 'economic-database-schema.sql');
    if (!fs.existsSync(schemaPath)) {
      throw new Error(`Schema file not found: ${schemaPath}`);
    }
    
    const schemaSql = fs.readFileSync(schemaPath, 'utf8');
    console.log('📄 Schema file loaded');
    
    // Execute the schema - split by statement
    const statements = schemaSql
      .split(';')
      .filter(stmt => stmt.trim().length > 0)
      .filter(stmt => !stmt.trim().startsWith('--'));
    
    console.log(`📊 Executing ${statements.length} SQL statements...`);
    
    for (let i = 0; i < statements.length; i++) {
      const statement = statements[i].trim();
      if (statement.length === 0) continue;
      
      try {
        await query(statement);
        if (statement.toLowerCase().includes('create table')) {
          const tableName = statement.match(/create table\s+(?:if not exists\s+)?(\w+)/i)?.[1];
          console.log(`✅ Table created: ${tableName}`);
        } else if (statement.toLowerCase().includes('insert into')) {
          const tableName = statement.match(/insert into\s+(\w+)/i)?.[1];
          console.log(`📥 Data inserted into: ${tableName}`);
        }
      } catch (error) {
        console.error(`❌ Error executing statement ${i + 1}:`, error.message);
        console.error(`Statement: ${statement.substring(0, 100)}...`);
        throw error;
      }
    }
    
    // Verify tables were created
    console.log('🔍 Verifying tables...');
    const tableCheck = await query(`
      SELECT table_name 
      FROM information_schema.tables 
      WHERE table_schema = 'public' 
        AND table_name IN ('economic_indicators', 'economic_calendar', 'market_correlations', 'economic_forecasts', 'recession_probabilities', 'economic_scenarios')
      ORDER BY table_name
    `);
    
    console.log('✅ Tables verified:');
    tableCheck.rows.forEach(row => {
      console.log(`  - ${row.table_name}`);
    });
    
    // Check data was inserted
    const dataCheck = await query(`
      SELECT 
        'economic_indicators' as table_name,
        COUNT(*) as record_count
      FROM economic_indicators
      UNION ALL
      SELECT 
        'economic_calendar' as table_name,
        COUNT(*) as record_count  
      FROM economic_calendar
      UNION ALL
      SELECT 
        'recession_probabilities' as table_name,
        COUNT(*) as record_count
      FROM recession_probabilities
      UNION ALL
      SELECT 
        'economic_scenarios' as table_name,
        COUNT(*) as record_count
      FROM economic_scenarios
      ORDER BY table_name
    `);
    
    console.log('📊 Data verification:');
    dataCheck.rows.forEach(row => {
      console.log(`  - ${row.table_name}: ${row.record_count} records`);
    });
    
    console.log('🎉 Economic database setup completed successfully!');
    
    // Try to populate with real data if population service is available
    try {
      console.log('🔄 Attempting to populate with real economic data...');
      const EconomicDataPopulationService = require('../services/economicDataPopulationService');
      const populationService = new EconomicDataPopulationService();
      
      const result = await populationService.updateRecentData(1); // Just 1 month for initial setup
      console.log(`📈 Population result: ${result.success.length} indicators populated, ${result.errors.length} errors`);
      
      if (result.errors.length > 0) {
        console.log('⚠️ Some indicators failed to populate (this is normal with demo API keys):');
        result.errors.slice(0, 3).forEach(error => {
          console.log(`  - ${error.indicator}: ${error.error}`);
        });
      }
      
    } catch (populationError) {
      console.log('ℹ️ Real data population not available (demo mode):', populationError.message);
    }
    
    return {
      success: true,
      tables: tableCheck.rows.length,
      seedData: dataCheck.rows
    };
    
  } catch (error) {
    console.error('❌ Failed to setup economic database:', error);
    throw error;
  }
}

// Run if called directly
if (require.main === module) {
  setupEconomicDatabase()
    .then((result) => {
      console.log('✅ Setup completed:', result);
      process.exit(0);
    })
    .catch((error) => {
      console.error('❌ Setup failed:', error);
      process.exit(1);
    });
}

module.exports = { setupEconomicDatabase };