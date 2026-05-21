const { Pool } = require('pg');

const pool = new Pool({
  host: 'localhost',
  port: 5432,
  user: 'postgres',
  password: process.env.DB_PASSWORD || '',
  database: 'stocks',
  ssl: false
});

async function populateTestData() {
  try {
    console.log('Populating test data for all 10K stocks...\n');

    // Get all stocks from stock_scores
    const stocksResult = await pool.query('SELECT DISTINCT symbol FROM stock_scores ORDER BY symbol');
    const stocks = stocksResult.rows.map(r => r.symbol);
    console.log(`Found ${stocks.length} stocks to populate\n`);

    // Clear tables
    console.log('Clearing existing data...');
    await pool.query('DELETE FROM key_metrics');
    await pool.query('DELETE FROM value_metrics');
    await pool.query('DELETE FROM quality_metrics');
    console.log('✓ Cleared\n');

    // Populate key_metrics with ticker and symbol
    console.log('1. Populating key_metrics...');
    for (let i = 0; i < stocks.length; i += 500) {
      const batch = stocks.slice(i, i + 500);
      const values = batch.map(sym =>
        `('${sym}', '${sym}', ${Math.floor(1000000000 + Math.random() * 500000000000)}, ${Math.random() * 30}, ${20 + Math.random() * 60}, NOW())`
      ).join(',');
      await pool.query(`
        INSERT INTO key_metrics (ticker, symbol, market_cap, held_percent_insiders, held_percent_institutions, created_at)
        VALUES ${values}
      `);
      process.stdout.write(`  ${Math.min(i + 500, stocks.length)}/${stocks.length}\r`);
    }
    console.log(`  ✓ ${stocks.length} rows\n`);

    // Populate value_metrics
    console.log('2. Populating value_metrics...');
    for (let i = 0; i < stocks.length; i += 500) {
      const batch = stocks.slice(i, i + 500);
      const values = batch.map(sym =>
        `('${sym}', ${10 + Math.random() * 50}, ${0.5 + Math.random() * 5}, ${0.5 + Math.random() * 5}, ${0.5 + Math.random() * 3}, ${Math.random() * 5}, ${Math.random() * 10}, NOW())`
      ).join(',');
      await pool.query(`
        INSERT INTO value_metrics (symbol, pe_ratio, pb_ratio, ps_ratio, peg_ratio, dividend_yield, fcf_yield, created_at)
        VALUES ${values}
      `);
      process.stdout.write(`  ${Math.min(i + 500, stocks.length)}/${stocks.length}\r`);
    }
    console.log(`  ✓ ${stocks.length} rows\n`);

    // Populate quality_metrics
    console.log('3. Populating quality_metrics...');
    for (let i = 0; i < stocks.length; i += 500) {
      const batch = stocks.slice(i, i + 500);
      const values = batch.map(sym =>
        `('${sym}', ${5 + Math.random() * 30}, ${3 + Math.random() * 25}, ${5 + Math.random() * 35}, ${2 + Math.random() * 20}, ${0.2 + Math.random() * 3}, ${1 + Math.random() * 3}, ${0.5 + Math.random() * 2.5}, ${2 + Math.random() * 8}, NOW())`
      ).join(',');
      await pool.query(`
        INSERT INTO quality_metrics (symbol, operating_margin, net_margin, roe, roa, debt_to_equity, current_ratio, quick_ratio, interest_coverage, created_at)
        VALUES ${values}
      `);
      process.stdout.write(`  ${Math.min(i + 500, stocks.length)}/${stocks.length}\r`);
    }
    console.log(`  ✓ ${stocks.length} rows\n`);

    console.log('✅ Test data population complete!\n');

  } catch (error) {
    console.error('❌ Error:', error.message);
  } finally {
    await pool.end();
  }
}

populateTestData();
