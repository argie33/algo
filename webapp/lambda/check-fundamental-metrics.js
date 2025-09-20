const { query } = require('./utils/database');

async function checkFundamentalMetrics() {
  try {
    const result = await query(`
      SELECT column_name, data_type
      FROM information_schema.columns
      WHERE table_name = 'fundamental_metrics'
      ORDER BY ordinal_position
    `);

    console.log('fundamental_metrics table structure:');
    result.rows.forEach(row => console.log(`- ${row.column_name}: ${row.data_type}`));

    // Check sample data
    const sampleData = await query(`
      SELECT * FROM fundamental_metrics LIMIT 3
    `);

    console.log('\nSample data:');
    if (sampleData.rows.length > 0) {
      console.log('Columns:', Object.keys(sampleData.rows[0]));
      sampleData.rows.forEach((row, i) => {
        console.log(`Row ${i + 1}:`, row);
      });
    } else {
      console.log('No data in fundamental_metrics table');
    }

    process.exit(0);
  } catch (error) {
    console.error('Error checking fundamental_metrics:', error);
    process.exit(1);
  }
}

checkFundamentalMetrics();