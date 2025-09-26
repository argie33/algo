const { query } = require('./utils/database');

async function fixDatabaseSchema() {
  console.log('🔧 Fixing database schema issues...');

  try {
    // Fix trading_strategies table - add missing columns if they don't exist
    console.log('Checking trading_strategies table...');

    // Check if strategy_type column exists
    try {
      await query(`ALTER TABLE trading_strategies ADD COLUMN IF NOT EXISTS strategy_type VARCHAR(50) NOT NULL DEFAULT 'basic'`);
      console.log('✅ Added/verified strategy_type column');
    } catch (error) {
      console.log('⚠️ strategy_type column already exists or error:', error.message);
    }

    // Check if hft_config column exists
    try {
      await query(`ALTER TABLE trading_strategies ADD COLUMN IF NOT EXISTS hft_config JSONB`);
      console.log('✅ Added/verified hft_config column');
    } catch (error) {
      console.log('⚠️ hft_config column already exists or error:', error.message);
    }

    // Fix technical_data_daily table - add missing columns if they don't exist
    console.log('Checking technical_data_daily table...');

    try {
      await query(`ALTER TABLE technical_data_daily ADD COLUMN IF NOT EXISTS price_vs_sma_200 DOUBLE PRECISION`);
      console.log('✅ Added/verified price_vs_sma_200 column');
    } catch (error) {
      console.log('⚠️ price_vs_sma_200 column already exists or error:', error.message);
    }

    try {
      await query(`ALTER TABLE technical_data_daily ADD COLUMN IF NOT EXISTS volume DOUBLE PRECISION`);
      console.log('✅ Added/verified volume column');
    } catch (error) {
      console.log('⚠️ volume column already exists or error:', error.message);
    }

    try {
      await query(`ALTER TABLE technical_data_daily ADD COLUMN IF NOT EXISTS price DOUBLE PRECISION`);
      console.log('✅ Added/verified price column');
    } catch (error) {
      console.log('⚠️ price column already exists or error:', error.message);
    }

    // Fix economic_data table - ensure it has all required columns
    console.log('Checking economic_data table...');

    try {
      await query(`ALTER TABLE economic_data ADD COLUMN IF NOT EXISTS category VARCHAR(50)`);
      console.log('✅ Added/verified category column');
    } catch (error) {
      console.log('⚠️ category column already exists or error:', error.message);
    }

    try {
      await query(`ALTER TABLE economic_data ADD COLUMN IF NOT EXISTS description TEXT`);
      console.log('✅ Added/verified description column');
    } catch (error) {
      console.log('⚠️ description column already exists or error:', error.message);
    }

    // Check if economic_data table has data, if not, insert some sample data
    const economicCountResult = await query("SELECT COUNT(*) as count FROM economic_data");
    const economicCount = parseInt(economicCountResult.rows[0].count);

    if (economicCount === 0) {
      console.log('📊 Inserting sample economic data...');
      await query(`
        INSERT INTO economic_data (series_id, date, value, description, category, frequency) VALUES
        ('GDP', '2025-09-01', 23500, 'Gross Domestic Product', 'economic', 'quarterly'),
        ('CPI', '2025-09-01', 307.789, 'Consumer Price Index', 'economic', 'monthly'),
        ('UNRATE', '2025-09-01', 3.8, 'Unemployment Rate', 'economic', 'monthly'),
        ('FEDFUNDS', '2025-09-01', 5.25, 'Federal Funds Rate', 'economic', 'monthly'),
        ('DGS10', '2025-09-01', 4.35, '10-Year Treasury Rate', 'economic', 'daily'),
        ('DGS2', '2025-09-01', 4.85, '2-Year Treasury Rate', 'economic', 'daily'),
        ('PAYEMS', '2025-09-01', 158450, 'Total Nonfarm Payrolls', 'economic', 'monthly'),
        ('HOUST', '2025-09-01', 1420, 'Housing Starts', 'economic', 'monthly'),
        ('CPIAUCSL', '2025-09-01', 307.789, 'Consumer Price Index for All Urban Consumers', 'economic', 'monthly'),
        ('M2SL', '2025-09-01', 20800, 'M2 Money Supply', 'economic', 'monthly')
      `);
      console.log('✅ Sample economic data inserted');
    } else {
      console.log(`📊 Economic data already exists (${economicCount} records)`);
    }

    console.log('🎉 Database schema fixes completed!');

  } catch (error) {
    console.error('❌ Error fixing database schema:', error);
    throw error;
  }
}

// Run the fix if this script is called directly
if (require.main === module) {
  fixDatabaseSchema()
    .then(() => {
      console.log('✅ Database schema fix completed successfully');
      process.exit(0);
    })
    .catch((error) => {
      console.error('❌ Database schema fix failed:', error);
      process.exit(1);
    });
}

module.exports = { fixDatabaseSchema };