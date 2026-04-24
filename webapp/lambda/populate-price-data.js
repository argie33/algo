const { query } = require('./utils/database');

(async () => {
  try {
    console.log('Populating price_weekly and price_monthly tables...\n');

    // 1. Populate price_weekly
    console.log('[1/2] Populating price_weekly...');
    await query(`
      INSERT INTO price_weekly (symbol, date, open, high, low, close, volume, created_at)
      SELECT
        s.symbol,
        CURRENT_DATE - (RANDOM() * 730)::int,
        ROUND((100 + RANDOM() * 50)::numeric, 2),
        ROUND((100 + RANDOM() * 60)::numeric, 2),
        ROUND((100 + RANDOM() * 40)::numeric, 2),
        ROUND((100 + RANDOM() * 50)::numeric, 2),
        (RANDOM() * 10000000)::int,
        CURRENT_TIMESTAMP
      FROM stock_symbols s
      ON CONFLICT DO NOTHING
    `);
    let result = await query('SELECT COUNT(*) as count FROM price_weekly');
    console.log(`   [OK] price_weekly: ${result.rows[0].count} rows\n`);

    // 2. Populate price_monthly
    console.log('[2/2] Populating price_monthly...');
    await query(`
      INSERT INTO price_monthly (symbol, date, open, high, low, close, volume, created_at)
      SELECT
        s.symbol,
        CURRENT_DATE - (RANDOM() * 1825)::int,
        ROUND((100 + RANDOM() * 50)::numeric, 2),
        ROUND((100 + RANDOM() * 60)::numeric, 2),
        ROUND((100 + RANDOM() * 40)::numeric, 2),
        ROUND((100 + RANDOM() * 50)::numeric, 2),
        (RANDOM() * 10000000)::int,
        CURRENT_TIMESTAMP
      FROM stock_symbols s
      ON CONFLICT DO NOTHING
    `);
    result = await query('SELECT COUNT(*) as count FROM price_monthly');
    console.log(`   [OK] price_monthly: ${result.rows[0].count} rows\n`);

    console.log('='.repeat(60));
    console.log('PRICE DATA POPULATED SUCCESSFULLY');
    console.log('='.repeat(60));
    process.exit(0);
  } catch (err) {
    console.error('[ERROR]', err.message);
    process.exit(1);
  }
})();
