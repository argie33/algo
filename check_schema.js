const { query } = require('./webapp/lambda/utils/database');

async function checkSchema() {
  try {
    // Check covered_call_opportunities columns
    console.log('\n=== COVERED_CALL_OPPORTUNITIES ===');
    const ccoResult = await query(`
      SELECT column_name, data_type
      FROM information_schema.columns
      WHERE table_name='covered_call_opportunities'
      ORDER BY ordinal_position
    `);
    if (ccoResult.rows.length === 0) {
      console.log('  Table does not exist or has no columns');
    } else {
      ccoResult.rows.forEach(row => console.log(`  ${row.column_name} (${row.data_type})`));
    }

    // Check earnings_history columns
    console.log('\n=== EARNINGS_HISTORY ===');
    const ehResult = await query(`
      SELECT column_name, data_type
      FROM information_schema.columns
      WHERE table_name='earnings_history'
      ORDER BY ordinal_position
    `);
    if (ehResult.rows.length === 0) {
      console.log('  Table does not exist or has no columns');
    } else {
      ehResult.rows.forEach(row => console.log(`  ${row.column_name} (${row.data_type})`));
    }

    process.exit(0);
  } catch (error) {
    console.error('Error:', error.message);
    process.exit(1);
  }
}

checkSchema();
