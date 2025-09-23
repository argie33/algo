const { query } = require('./webapp/lambda/utils/database');

async function checkSchemas() {
  console.log('🔍 Checking buy_sell table schemas...');

  try {
    // Check if tables exist
    const tables = ['buy_sell_daily', 'buy_sell_weekly', 'buy_sell_monthly'];

    for (const table of tables) {
      console.log(`\n📊 Checking ${table}:`);

      try {
        // Check columns
        const columnsQuery = `
          SELECT column_name, data_type
          FROM information_schema.columns
          WHERE table_name = '${table}'
          ORDER BY ordinal_position
        `;
        const columnsResult = await query(columnsQuery);

        if (columnsResult.rows && columnsResult.rows.length > 0) {
          console.log('  Columns:');
          columnsResult.rows.forEach(col => {
            console.log(`    - ${col.column_name}: ${col.data_type}`);
          });

          // Check if there's any data
          const countQuery = `SELECT COUNT(*) as count FROM ${table} LIMIT 1`;
          const countResult = await query(countQuery);
          console.log(`  Row count: ${countResult.rows[0].count}`);

          if (countResult.rows[0].count > 0) {
            // Get a sample row
            const sampleQuery = `SELECT * FROM ${table} LIMIT 1`;
            const sampleResult = await query(sampleQuery);
            console.log('  Sample data:', Object.keys(sampleResult.rows[0]));
          }
        } else {
          console.log(`  ❌ Table ${table} does not exist`);
        }
      } catch (error) {
        console.log(`  ❌ Error checking ${table}: ${error.message}`);
      }
    }

    console.log('\n✅ Schema check complete');
    process.exit(0);
  } catch (error) {
    console.error('Error:', error);
    process.exit(1);
  }
}

checkSchemas();