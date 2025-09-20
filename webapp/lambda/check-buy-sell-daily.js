const { query } = require('./utils/database');

async function checkBuySellDaily() {
  try {
    const result = await query(`
      SELECT column_name, data_type
      FROM information_schema.columns
      WHERE table_name = 'buy_sell_daily'
      ORDER BY ordinal_position
    `);

    console.log('buy_sell_daily table structure:');
    result.rows.forEach(row => console.log(`- ${row.column_name}: ${row.data_type}`));

    // Check sample data
    const sampleData = await query(`
      SELECT * FROM buy_sell_daily LIMIT 3
    `);

    console.log('\nSample data:');
    if (sampleData.rows.length > 0) {
      console.log('Columns:', Object.keys(sampleData.rows[0]));
      sampleData.rows.forEach((row, i) => {
        console.log(`Row ${i + 1}:`, row);
      });
    } else {
      console.log('No data in buy_sell_daily table');
    }

    process.exit(0);
  } catch (error) {
    console.error('Error checking buy_sell_daily:', error);
    process.exit(1);
  }
}

checkBuySellDaily();