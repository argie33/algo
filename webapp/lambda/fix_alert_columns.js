const { initializeDatabase, closeDatabase } = require('./utils/database');

async function fixAlertColumns() {
  console.log('🔧 Fixing missing alert columns...');

  try {
    await initializeDatabase();

    const { query } = require('./utils/database');

    // Add missing columns to user_alerts table
    console.log('Adding is_active column to user_alerts...');
    await query(`ALTER TABLE user_alerts ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true`);

    // Add missing columns to signal_alerts table
    console.log('Adding status column to signal_alerts...');
    await query(`ALTER TABLE signal_alerts ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'active'`);

    // Add primary key constraint to market_data if it doesn't exist
    console.log('Checking market_data table constraints...');
    const constraintCheck = await query(`
      SELECT constraint_name
      FROM information_schema.table_constraints
      WHERE table_name = 'market_data'
      AND constraint_type = 'PRIMARY KEY'
    `);

    if (constraintCheck.rows.length === 0) {
      console.log('Adding primary key to market_data table...');
      await query(`ALTER TABLE market_data ADD CONSTRAINT market_data_pkey PRIMARY KEY (ticker, date)`);
    }

    // Try to create the indexes again now that columns exist
    console.log('Creating indexes on new columns...');
    await query(`CREATE INDEX IF NOT EXISTS idx_user_alerts_active ON user_alerts(is_active)`);
    await query(`CREATE INDEX IF NOT EXISTS idx_signal_alerts_active ON signal_alerts(status)`);

    console.log('✅ Alert column fixes completed successfully');

  } catch (error) {
    console.error('❌ Error fixing alert columns:', error);
  } finally {
    await closeDatabase();
  }
}

fixAlertColumns().catch(console.error);