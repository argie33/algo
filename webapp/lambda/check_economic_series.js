const { query } = require('./utils/database');

function resolveSeriesId(input) {
  if (!input) return input;
  const SERIES_MAPPING = {
    'GDP': 'GDPC1',
    'CPI': 'CPIAUCSL',
    'UNEMPLOYMENT': 'UNRATE',
  };
  const upperInput = input.toUpperCase();
  return SERIES_MAPPING[upperInput] || input;
}

async function checkEconomicSeries() {
  try {
    console.log('🔍 Checking available economic series in database...');

    // Get all distinct series_ids from the database
    const result = await query('SELECT DISTINCT series_id FROM economic_data ORDER BY series_id');

    console.log('📊 Available series in database:');
    result.rows.forEach(row => {
      console.log(`  - ${row.series_id}`);
    });

    console.log(`\n📈 Total series: ${result.rows.length}`);

    // Test if GDP resolves correctly
    console.log('\n🔍 Testing series resolution:');

    const testCases = ['GDP', 'CPI', 'UNRATE'];
    for (const testCase of testCases) {
      const resolved = resolveSeriesId(testCase);
      console.log(`  ${testCase} -> ${resolved}`);

      // Check if resolved series exists in database
      const checkResult = await query('SELECT COUNT(*) as count FROM economic_data WHERE series_id = $1', [resolved]);
      const count = parseInt(checkResult.rows[0].count);
      console.log(`    Database has ${count} records for ${resolved}`);
    }

  } catch (error) {
    console.error('❌ Error:', error.message);
  }

  process.exit(0);
}

checkEconomicSeries();