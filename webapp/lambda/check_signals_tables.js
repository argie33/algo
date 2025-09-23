const { query } = require('./utils/database');

async function checkSignalTables() {
  try {
    console.log('🔍 Checking for signal tables...');

    // Check if buy_sell_daily table exists
    const tableCheck = await query(`
      SELECT table_name
      FROM information_schema.tables
      WHERE table_schema = 'public'
      AND table_name LIKE 'buy_sell%'
      ORDER BY table_name;
    `);

    console.log('Found tables:', tableCheck.rows.map(r => r.table_name));

    if (tableCheck.rows.length === 0) {
      console.log('❌ No buy_sell tables found');
      return;
    }

    // Check data in buy_sell_daily if it exists
    const dailyTable = tableCheck.rows.find(r => r.table_name === 'buy_sell_daily');
    if (dailyTable) {
      console.log('\n📊 Checking buy_sell_daily data...');
      const dataCheck = await query('SELECT COUNT(*) as count FROM buy_sell_daily LIMIT 1');
      console.log('Rows in buy_sell_daily:', dataCheck.rows[0].count);

      const sampleData = await query('SELECT * FROM buy_sell_daily LIMIT 3');
      console.log('Sample data:', sampleData.rows);
    }

  } catch (error) {
    console.error('Error checking tables:', error.message);
  }

  process.exit(0);
}

checkSignalTables();