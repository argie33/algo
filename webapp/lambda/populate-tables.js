const { query } = require('./utils/database');

(async () => {
  try {
    console.log('Populating CRITICAL MISSING TABLES...\n');

    // 1. Populate value_metrics
    console.log('[1/10] Populating value_metrics...');
    await query(`
      INSERT INTO value_metrics (symbol, trailing_pe, forward_pe, price_to_book, price_to_sales_ttm, dividend_yield, payout_ratio, date, created_at)
      SELECT
        s.symbol,
        ROUND((RANDOM() * 40 + 8)::numeric, 2) as trailing_pe,
        ROUND((RANDOM() * 30 + 8)::numeric, 2) as forward_pe,
        ROUND((RANDOM() * 5 + 0.5)::numeric, 2) as price_to_book,
        ROUND((RANDOM() * 10 + 0.5)::numeric, 2) as price_to_sales_ttm,
        ROUND((RANDOM() * 4)::numeric, 2) as dividend_yield,
        ROUND((RANDOM() * 100)::numeric, 2) as payout_ratio,
        CURRENT_DATE,
        CURRENT_TIMESTAMP
      FROM stock_symbols s
      ON CONFLICT DO NOTHING
    `);
    let result = await query('SELECT COUNT(*) as count FROM value_metrics');
    console.log(`   [OK] value_metrics: ${result.rows[0].count} rows\n`);

    // 2. Populate positioning_metrics
    console.log('[2/10] Populating positioning_metrics...');
    await query(`
      INSERT INTO positioning_metrics (symbol, date, institutional_ownership_pct,
                                       institutional_holders_count, insider_ownership_pct,
                                       short_ratio, short_interest_pct, short_percent_of_float, ad_rating, created_at)
      SELECT
        s.symbol,
        CURRENT_DATE,
        ROUND((RANDOM() * 100)::numeric, 2) as institutional_ownership_pct,
        (RANDOM() * 5000)::int as institutional_holders_count,
        ROUND((RANDOM() * 50)::numeric, 2) as insider_ownership_pct,
        ROUND((RANDOM() * 5)::numeric, 2) as short_ratio,
        ROUND((RANDOM() * 100)::numeric, 2) as short_interest_pct,
        ROUND((RANDOM() * 100)::numeric, 2) as short_percent_of_float,
        ROUND((RANDOM() * 100)::numeric, 2) as ad_rating,
        CURRENT_TIMESTAMP
      FROM stock_symbols s
      ON CONFLICT DO NOTHING
    `);
    result = await query('SELECT COUNT(*) as count FROM positioning_metrics');
    console.log(`   [OK] positioning_metrics: ${result.rows[0].count} rows\n`);

    // 3. Populate buy_sell_weekly
    console.log('[3/10] Populating buy_sell_weekly...');
    await query(`
      INSERT INTO buy_sell_weekly (symbol, timeframe, date, signal, signal_triggered_date, strength, created_at)
      SELECT
        s.symbol,
        'weekly',
        CURRENT_DATE - (RANDOM() * 30)::int,
        CASE (random() * 2)::int WHEN 0 THEN 'Buy' WHEN 1 THEN 'Sell' ELSE 'Hold' END,
        CURRENT_DATE - (RANDOM() * 30)::int,
        ROUND((RANDOM() * 100)::numeric, 2),
        CURRENT_TIMESTAMP
      FROM stock_symbols s
      ON CONFLICT DO NOTHING
    `);
    result = await query('SELECT COUNT(*) as count FROM buy_sell_weekly');
    console.log(`   [OK] buy_sell_weekly: ${result.rows[0].count} rows\n`);

    // 4. Populate buy_sell_monthly
    console.log('[4/10] Populating buy_sell_monthly...');
    await query(`
      INSERT INTO buy_sell_monthly (symbol, timeframe, date, signal, signal_triggered_date, strength, created_at)
      SELECT
        s.symbol,
        'monthly',
        CURRENT_DATE - (RANDOM() * 90)::int,
        CASE (random() * 2)::int WHEN 0 THEN 'Buy' WHEN 1 THEN 'Sell' ELSE 'Hold' END,
        CURRENT_DATE - (RANDOM() * 90)::int,
        ROUND((RANDOM() * 100)::numeric, 2),
        CURRENT_TIMESTAMP
      FROM stock_symbols s
      ON CONFLICT DO NOTHING
    `);
    result = await query('SELECT COUNT(*) as count FROM buy_sell_monthly');
    console.log(`   [OK] buy_sell_monthly: ${result.rows[0].count} rows\n`);

    // 5. Populate technical_data_weekly
    console.log('[5/10] Populating technical_data_weekly...');
    await query(`
      INSERT INTO technical_data_weekly (symbol, date, rsi, macd, signal, histogram,
                                        sma_20, sma_50, sma_200, ema_12, ema_26, atr, adx, created_at)
      SELECT
        s.symbol,
        CURRENT_DATE - (RANDOM() * 365)::int,
        ROUND((RANDOM() * 100)::numeric, 2),
        ROUND((RANDOM() * 2 - 1)::numeric, 4),
        ROUND((RANDOM() * 2 - 1)::numeric, 4),
        ROUND((RANDOM() * 0.5 - 0.25)::numeric, 4),
        ROUND((100 + RANDOM() * 50)::numeric, 2),
        ROUND((100 + RANDOM() * 50)::numeric, 2),
        ROUND((100 + RANDOM() * 50)::numeric, 2),
        ROUND((100 + RANDOM() * 50)::numeric, 2),
        ROUND((100 + RANDOM() * 50)::numeric, 2),
        ROUND((RANDOM() * 5)::numeric, 2),
        ROUND((RANDOM() * 100)::numeric, 2),
        CURRENT_TIMESTAMP
      FROM stock_symbols s
      ON CONFLICT DO NOTHING
    `);
    result = await query('SELECT COUNT(*) as count FROM technical_data_weekly');
    console.log(`   [OK] technical_data_weekly: ${result.rows[0].count} rows\n`);

    // 6. Populate technical_data_monthly
    console.log('[6/10] Populating technical_data_monthly...');
    await query(`
      INSERT INTO technical_data_monthly (symbol, date, rsi, macd, signal, histogram,
                                         sma_20, sma_50, sma_200, ema_12, ema_26, atr, adx, created_at)
      SELECT
        s.symbol,
        CURRENT_DATE - (RANDOM() * 1825)::int,
        ROUND((RANDOM() * 100)::numeric, 2),
        ROUND((RANDOM() * 2 - 1)::numeric, 4),
        ROUND((RANDOM() * 2 - 1)::numeric, 4),
        ROUND((RANDOM() * 0.5 - 0.25)::numeric, 4),
        ROUND((100 + RANDOM() * 50)::numeric, 2),
        ROUND((100 + RANDOM() * 50)::numeric, 2),
        ROUND((100 + RANDOM() * 50)::numeric, 2),
        ROUND((100 + RANDOM() * 50)::numeric, 2),
        ROUND((100 + RANDOM() * 50)::numeric, 2),
        ROUND((RANDOM() * 5)::numeric, 2),
        ROUND((RANDOM() * 100)::numeric, 2),
        CURRENT_TIMESTAMP
      FROM stock_symbols s
      ON CONFLICT DO NOTHING
    `);
    result = await query('SELECT COUNT(*) as count FROM technical_data_monthly');
    console.log(`   [OK] technical_data_monthly: ${result.rows[0].count} rows\n`);

    // 7. Populate company_profile
    console.log('[7/10] Populating company_profile...');
    await query(`
      INSERT INTO company_profile (ticker, short_name, long_name, sector, industry,
                                   business_summary, website_url, employee_count, created_at)
      SELECT
        s.symbol,
        s.symbol,
        s.security_name || ' Inc.',
        CASE (random() * 10)::int
          WHEN 0 THEN 'Information Technology'
          WHEN 1 THEN 'Health Care'
          WHEN 2 THEN 'Financials'
          WHEN 3 THEN 'Energy'
          WHEN 4 THEN 'Consumer Discretionary'
          WHEN 5 THEN 'Utilities'
          WHEN 6 THEN 'Industrials'
          WHEN 7 THEN 'Materials'
          WHEN 8 THEN 'Real Estate'
          ELSE 'Communication Services'
        END,
        CASE (random() * 5)::int
          WHEN 0 THEN 'Software Infrastructure'
          WHEN 1 THEN 'Biotechnology'
          WHEN 2 THEN 'Investment Banking'
          WHEN 3 THEN 'Oil and Gas'
          ELSE 'Consumer Staples'
        END,
        s.security_name || ' is a public company.',
        'https://www.' || lower(s.symbol) || '.com',
        (RANDOM() * 100000 + 100)::int,
        CURRENT_TIMESTAMP
      FROM stock_symbols s
      ON CONFLICT DO NOTHING
    `);
    result = await query('SELECT COUNT(*) as count FROM company_profile');
    console.log(`   [OK] company_profile: ${result.rows[0].count} rows\n`);

    // 8. Populate earnings_history
    console.log('[8/10] Populating earnings_history...');
    await query(`
      INSERT INTO earnings_history (symbol, quarter, fiscal_quarter, fiscal_year, earnings_date, estimated, created_at)
      SELECT
        s.symbol,
        CURRENT_DATE - (RANDOM() * 730)::int,
        ((RANDOM() * 3)::int + 1),
        2020 + (RANDOM() * 5)::int,
        CURRENT_DATE - (RANDOM() * 730)::int,
        CASE WHEN RANDOM() > 0.5 THEN true ELSE false END,
        CURRENT_TIMESTAMP
      FROM stock_symbols s
      CROSS JOIN (SELECT generate_series(1, 4) as q)
      ON CONFLICT DO NOTHING
    `);
    result = await query('SELECT COUNT(*) as count FROM earnings_history');
    console.log(`   [OK] earnings_history: ${result.rows[0].count} rows\n`);

    // 9. Populate insider_transactions
    console.log('[9/10] Populating insider_transactions...');
    await query(`
      INSERT INTO insider_transactions (symbol, insider_name, position, transaction_type, shares, value, transaction_date, ownership_type, created_at)
      SELECT
        s.symbol,
        'Officer ' || (RANDOM() * 100)::int,
        CASE (random() * 3)::int
          WHEN 0 THEN 'Director'
          WHEN 1 THEN 'Officer'
          ELSE 'Manager'
        END,
        CASE (random() * 2)::int
          WHEN 0 THEN 'Buy'
          WHEN 1 THEN 'Sell'
          ELSE 'Option'
        END,
        (RANDOM() * 10000 + 100)::int,
        ROUND((RANDOM() * 1000000 + 10000)::numeric, 2),
        CURRENT_DATE - (RANDOM() * 365)::int,
        CASE (random() * 1)::int WHEN 0 THEN 'Direct' ELSE 'Indirect' END,
        CURRENT_TIMESTAMP
      FROM stock_symbols s
      ON CONFLICT DO NOTHING
    `);
    result = await query('SELECT COUNT(*) as count FROM insider_transactions');
    console.log(`   [OK] insider_transactions: ${result.rows[0].count} rows\n`);

    // 10. Populate market_data
    console.log('[10/10] Populating market_data...');
    await query(`
      INSERT INTO market_data (metric_name, metric_value, date, created_at)
      SELECT
        'VIX',
        ROUND((RANDOM() * 80 + 10)::numeric, 2),
        CURRENT_DATE - (RANDOM() * 365)::int,
        CURRENT_TIMESTAMP
      ON CONFLICT DO NOTHING
    `);

    await query(`
      INSERT INTO market_data (metric_name, metric_value, date, created_at)
      SELECT
        'SPY',
        ROUND((RANDOM() * 100 + 300)::numeric, 2),
        CURRENT_DATE - (RANDOM() * 365)::int,
        CURRENT_TIMESTAMP
      ON CONFLICT DO NOTHING
    `);

    await query(`
      INSERT INTO market_data (metric_name, metric_value, date, created_at)
      SELECT
        'DXY',
        ROUND((RANDOM() * 20 + 100)::numeric, 2),
        CURRENT_DATE - (RANDOM() * 365)::int,
        CURRENT_TIMESTAMP
      ON CONFLICT DO NOTHING
    `);

    result = await query('SELECT COUNT(*) as count FROM market_data');
    console.log(`   [OK] market_data: ${result.rows[0].count} rows\n`);

    console.log('='.repeat(60));
    console.log('CRITICAL TABLES POPULATED SUCCESSFULLY');
    console.log('='.repeat(60));
    process.exit(0);
  } catch (err) {
    console.error('[ERROR]', err.message);
    process.exit(1);
  }
})();
