
const { query } = require('./utils/database');

async function checkAWSTables() {
  try {
    console.log('🔍 Checking available tables in AWS database...\n');

    const result = await query(`
      SELECT table_name
      FROM information_schema.tables
      WHERE table_schema = 'public'
      ORDER BY table_name
    `);

    console.log('📊 Available tables:');
    console.log('==================');
    result.rows.forEach(row => {
      console.log(`✅ ${row.table_name}`);
    });

    console.log(`\n📈 Total tables: ${result.rows.length}`);

    // Check for specific tables we need
    const tables = result.rows.map(row => row.table_name);
    const criticalTables = ['technical_data_daily', 'market_data', 'company_profile', 'daily_returns', 'options_data'];

    console.log('\n🔍 Checking critical tables:');
    console.log('============================');
    criticalTables.forEach(table => {
      if (tables.includes(table)) {
        console.log(`✅ ${table} - EXISTS`);
      } else {
        console.log(`❌ ${table} - MISSING`);
      }
    });

  } catch (error) {
    console.error('❌ Error checking tables:', error.message);
  }
}

checkAWSTables();