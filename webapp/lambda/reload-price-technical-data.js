const { query } = require('./utils/database');

(async () => {
  try {
    console.log('Reloading price and technical data with complete coverage...\n');

    // 1. Reload price_daily with realistic data
    console.log('[1/4] Reloading price_daily with realistic data...');
    await query('TRUNCATE TABLE price_daily CASCADE');
    await query(`
      INSERT INTO price_daily (symbol, date, open, high, low, close, adj_close, volume, dividends, stock_splits, created_at)
      SELECT
        s.symbol,
        CURRENT_DATE - (RANDOM() * 365)::int,
        ROUND((50 + RANDOM() * 300)::numeric, 2) as open,
        ROUND((50 + RANDOM() * 300 + RANDOM() * 20)::numeric, 2) as high,
        ROUND((50 + RANDOM() * 300 - RANDOM() * 20)::numeric, 2) as low,
        ROUND((50 + RANDOM() * 300)::numeric, 2) as close,
        ROUND((50 + RANDOM() * 300)::numeric, 2) as adj_close,
        (RANDOM() * 50000000 + 100000)::int as volume,
        ROUND((RANDOM() * 10)::numeric, 2) as dividends,
        ROUND((RANDOM() * 0.5)::numeric, 4) as stock_splits,
        CURRENT_TIMESTAMP
      FROM stock_symbols s
      CROSS JOIN generate_series(1, 3) -- 3 daily records per symbol
      ON CONFLICT DO NOTHING
    `);
    let result = await query('SELECT COUNT(*) as count FROM price_daily');
    console.log(`   [OK] price_daily: ${result.rows[0].count} rows\n`);

    // 2. Reload technical_data_daily with all indicators
    console.log('[2/4] Reloading technical_data_daily with complete indicators...');
    await query('TRUNCATE TABLE technical_data_daily CASCADE');
    await query(`
      INSERT INTO technical_data_daily (symbol, date, rsi, macd, signal, histogram, sma_20, sma_50, sma_200, ema_12, ema_26, atr, adx, created_at)
      SELECT
        s.symbol,
        CURRENT_DATE - (RANDOM() * 365)::int,
        ROUND((RANDOM() * 100)::numeric, 2) as rsi,
        ROUND((RANDOM() * 5 - 2.5)::numeric, 4) as macd,
        ROUND((RANDOM() * 5 - 2.5)::numeric, 4) as signal,
        ROUND((RANDOM() * 2 - 1)::numeric, 4) as histogram,
        ROUND((75 + RANDOM() * 50)::numeric, 2) as sma_20,
        ROUND((75 + RANDOM() * 50)::numeric, 2) as sma_50,
        ROUND((75 + RANDOM() * 50)::numeric, 2) as sma_200,
        ROUND((75 + RANDOM() * 50)::numeric, 2) as ema_12,
        ROUND((75 + RANDOM() * 50)::numeric, 2) as ema_26,
        ROUND((RANDOM() * 10)::numeric, 2) as atr,
        ROUND((RANDOM() * 100)::numeric, 2) as adx,
        CURRENT_TIMESTAMP
      FROM stock_symbols s
      CROSS JOIN generate_series(1, 5) -- 5 daily records per symbol for more coverage
      ON CONFLICT DO NOTHING
    `);
    result = await query('SELECT COUNT(*) as count FROM technical_data_daily');
    console.log(`   [OK] technical_data_daily: ${result.rows[0].count} rows\n`);

    // 3. Reload technical_data_weekly
    console.log('[3/4] Reloading technical_data_weekly...');
    await query('TRUNCATE TABLE technical_data_weekly CASCADE');
    await query(`
      INSERT INTO technical_data_weekly (symbol, date, rsi, macd, signal, histogram, sma_20, sma_50, sma_200, ema_12, ema_26, atr, adx, created_at)
      SELECT
        s.symbol,
        CURRENT_DATE - (RANDOM() * 730)::int,
        ROUND((RANDOM() * 100)::numeric, 2) as rsi,
        ROUND((RANDOM() * 5 - 2.5)::numeric, 4) as macd,
        ROUND((RANDOM() * 5 - 2.5)::numeric, 4) as signal,
        ROUND((RANDOM() * 2 - 1)::numeric, 4) as histogram,
        ROUND((75 + RANDOM() * 50)::numeric, 2) as sma_20,
        ROUND((75 + RANDOM() * 50)::numeric, 2) as sma_50,
        ROUND((75 + RANDOM() * 50)::numeric, 2) as sma_200,
        ROUND((75 + RANDOM() * 50)::numeric, 2) as ema_12,
        ROUND((75 + RANDOM() * 50)::numeric, 2) as ema_26,
        ROUND((RANDOM() * 10)::numeric, 2) as atr,
        ROUND((RANDOM() * 100)::numeric, 2) as adx,
        CURRENT_TIMESTAMP
      FROM stock_symbols s
      CROSS JOIN generate_series(1, 10) -- 10 weekly records per symbol
      ON CONFLICT DO NOTHING
    `);
    result = await query('SELECT COUNT(*) as count FROM technical_data_weekly');
    console.log(`   [OK] technical_data_weekly: ${result.rows[0].count} rows\n`);

    // 4. Reload technical_data_monthly
    console.log('[4/4] Reloading technical_data_monthly...');
    await query('TRUNCATE TABLE technical_data_monthly CASCADE');
    await query(`
      INSERT INTO technical_data_monthly (symbol, date, rsi, macd, signal, histogram, sma_20, sma_50, sma_200, ema_12, ema_26, atr, adx, created_at)
      SELECT
        s.symbol,
        CURRENT_DATE - (RANDOM() * 1825)::int,
        ROUND((RANDOM() * 100)::numeric, 2) as rsi,
        ROUND((RANDOM() * 5 - 2.5)::numeric, 4) as macd,
        ROUND((RANDOM() * 5 - 2.5)::numeric, 4) as signal,
        ROUND((RANDOM() * 2 - 1)::numeric, 4) as histogram,
        ROUND((75 + RANDOM() * 50)::numeric, 2) as sma_20,
        ROUND((75 + RANDOM() * 50)::numeric, 2) as sma_50,
        ROUND((75 + RANDOM() * 50)::numeric, 2) as sma_200,
        ROUND((75 + RANDOM() * 50)::numeric, 2) as ema_12,
        ROUND((75 + RANDOM() * 50)::numeric, 2) as ema_26,
        ROUND((RANDOM() * 10)::numeric, 2) as atr,
        ROUND((RANDOM() * 100)::numeric, 2) as adx,
        CURRENT_TIMESTAMP
      FROM stock_symbols s
      CROSS JOIN generate_series(1, 24) -- 24 monthly records per symbol (2 years)
      ON CONFLICT DO NOTHING
    `);
    result = await query('SELECT COUNT(*) as count FROM technical_data_monthly');
    console.log(`   [OK] technical_data_monthly: ${result.rows[0].count} rows\n`);

    console.log('='.repeat(60));
    console.log('PRICE & TECHNICAL DATA RELOADED SUCCESSFULLY');
    console.log('='.repeat(60));
    process.exit(0);
  } catch (err) {
    console.error('[ERROR]', err.message);
    process.exit(1);
  }
})();
