const { initializeDatabase, closeDatabase, query } = require('./utils/database');

async function checkTradingStrategies() {
  console.log('🔧 Checking trading_strategies table...');

  try {
    await initializeDatabase();

    // Check table structure
    console.log('Checking trading_strategies table structure...');
    const tableInfo = await query(`
      SELECT column_name, data_type, is_nullable, column_default
      FROM information_schema.columns
      WHERE table_name = 'trading_strategies'
      ORDER BY ordinal_position
    `);

    console.log('Trading strategies table columns:');
    tableInfo.rows.forEach(row => {
      console.log(`  ${row.column_name}: ${row.data_type} (nullable: ${row.is_nullable}, default: ${row.column_default})`);
    });

    // Check if there are any existing records with NULL strategy_type
    console.log('\nChecking for NULL strategy_type records...');
    const nullRecords = await query(`
      SELECT id, user_id, strategy_name, strategy_type
      FROM trading_strategies
      WHERE strategy_type IS NULL
      LIMIT 5
    `);

    console.log(`Found ${nullRecords.rows.length} records with NULL strategy_type`);
    nullRecords.rows.forEach(row => {
      console.log(`  ID: ${row.id}, User: ${row.user_id}, Name: ${row.strategy_name}, Type: ${row.strategy_type}`);
    });

    // Check total record count
    const count = await query(`SELECT COUNT(*) as total FROM trading_strategies`);
    console.log(`\nTotal trading_strategies records: ${count.rows[0].total}`);

    console.log('✅ Trading strategies check completed');

  } catch (error) {
    console.error('❌ Error checking trading strategies:', error);
  } finally {
    await closeDatabase();
  }
}

checkTradingStrategies().catch(console.error);