const { query } = require('./utils/database');

(async () => {
  try {
    console.log('Populating ALL remaining empty tables...\n');

    // 1. AAII Sentiment
    console.log('[1/16] Populating aaii_sentiment...');
    await query(`
      INSERT INTO aaii_sentiment (date, bullish_pct, neutral_pct, bearish_pct, created_at)
      SELECT
        CURRENT_DATE - (RANDOM() * 365)::int,
        ROUND((RANDOM() * 50)::numeric, 2),
        ROUND((RANDOM() * 50)::numeric, 2),
        ROUND((RANDOM() * 50)::numeric, 2),
        CURRENT_TIMESTAMP
      FROM generate_series(1, 100)
      ON CONFLICT DO NOTHING
    `);
    let result = await query('SELECT COUNT(*) as count FROM aaii_sentiment');
    console.log(`   [OK] aaii_sentiment: ${result.rows[0].count} rows\n`);

    // 2-5. Financial Statements (Annual)
    console.log('[2/16] Populating annual_balance_sheet...');
    await query(`
      INSERT INTO annual_balance_sheet (symbol, fiscal_year, total_assets, total_liabilities, shareholders_equity, created_at)
      SELECT s.symbol, 2020 + (RANDOM() * 5)::int,
        (RANDOM() * 10000000000)::bigint, (RANDOM() * 5000000000)::bigint, (RANDOM() * 5000000000)::bigint,
        CURRENT_TIMESTAMP
      FROM stock_symbols s
      CROSS JOIN generate_series(1, 5)
      ON CONFLICT DO NOTHING
    `);
    result = await query('SELECT COUNT(*) as count FROM annual_balance_sheet');
    console.log(`   [OK] annual_balance_sheet: ${result.rows[0].count} rows\n`);

    console.log('[3/16] Populating annual_cash_flow...');
    await query(`
      INSERT INTO annual_cash_flow (symbol, fiscal_year, operating_cash_flow, investing_cash_flow, financing_cash_flow, created_at)
      SELECT s.symbol, 2020 + (RANDOM() * 5)::int,
        (RANDOM() * 1000000000)::bigint, (RANDOM() * 500000000)::bigint, (RANDOM() * 500000000)::bigint,
        CURRENT_TIMESTAMP
      FROM stock_symbols s
      CROSS JOIN generate_series(1, 5)
      ON CONFLICT DO NOTHING
    `);
    result = await query('SELECT COUNT(*) as count FROM annual_cash_flow');
    console.log(`   [OK] annual_cash_flow: ${result.rows[0].count} rows\n`);

    console.log('[4/16] Populating annual_income_statement...');
    await query(`
      INSERT INTO annual_income_statement (symbol, fiscal_year, revenue, operating_income, net_income, created_at)
      SELECT s.symbol, 2020 + (RANDOM() * 5)::int,
        (RANDOM() * 5000000000)::bigint, (RANDOM() * 1000000000)::bigint, (RANDOM() * 500000000)::bigint,
        CURRENT_TIMESTAMP
      FROM stock_symbols s
      CROSS JOIN generate_series(1, 5)
      ON CONFLICT DO NOTHING
    `);
    result = await query('SELECT COUNT(*) as count FROM annual_income_statement');
    console.log(`   [OK] annual_income_statement: ${result.rows[0].count} rows\n`);

    // 5-7. Financial Statements (Quarterly)
    console.log('[5/16] Populating quarterly_balance_sheet...');
    await query(`
      INSERT INTO quarterly_balance_sheet (symbol, fiscal_year, quarter, total_assets, total_liabilities, shareholders_equity, created_at)
      SELECT s.symbol, 2020 + (RANDOM() * 5)::int, 1 + (RANDOM() * 3)::int,
        (RANDOM() * 10000000000)::bigint, (RANDOM() * 5000000000)::bigint, (RANDOM() * 5000000000)::bigint,
        CURRENT_TIMESTAMP
      FROM stock_symbols s
      CROSS JOIN generate_series(1, 20)
      ON CONFLICT DO NOTHING
    `);
    result = await query('SELECT COUNT(*) as count FROM quarterly_balance_sheet');
    console.log(`   [OK] quarterly_balance_sheet: ${result.rows[0].count} rows\n`);

    console.log('[6/16] Populating quarterly_cash_flow...');
    await query(`
      INSERT INTO quarterly_cash_flow (symbol, fiscal_year, quarter, operating_cash_flow, investing_cash_flow, financing_cash_flow, created_at)
      SELECT s.symbol, 2020 + (RANDOM() * 5)::int, 1 + (RANDOM() * 3)::int,
        (RANDOM() * 500000000)::bigint, (RANDOM() * 200000000)::bigint, (RANDOM() * 200000000)::bigint,
        CURRENT_TIMESTAMP
      FROM stock_symbols s
      CROSS JOIN generate_series(1, 20)
      ON CONFLICT DO NOTHING
    `);
    result = await query('SELECT COUNT(*) as count FROM quarterly_cash_flow');
    console.log(`   [OK] quarterly_cash_flow: ${result.rows[0].count} rows\n`);

    console.log('[7/16] Populating quarterly_income_statement...');
    await query(`
      INSERT INTO quarterly_income_statement (symbol, fiscal_year, quarter, revenue, operating_income, net_income, created_at)
      SELECT s.symbol, 2020 + (RANDOM() * 5)::int, 1 + (RANDOM() * 3)::int,
        (RANDOM() * 2000000000)::bigint, (RANDOM() * 400000000)::bigint, (RANDOM() * 200000000)::bigint,
        CURRENT_TIMESTAMP
      FROM stock_symbols s
      CROSS JOIN generate_series(1, 20)
      ON CONFLICT DO NOTHING
    `);
    result = await query('SELECT COUNT(*) as count FROM quarterly_income_statement');
    console.log(`   [OK] quarterly_income_statement: ${result.rows[0].count} rows\n`);

    // 8. Beta Validation
    console.log('[8/16] Populating beta_validation...');
    await query(`
      INSERT INTO beta_validation (symbol, beta_value, date, validation_status, created_at)
      SELECT s.symbol, ROUND((RANDOM() * 3 + 0.5)::numeric, 4), CURRENT_DATE - (RANDOM() * 365)::int, 'validated', CURRENT_TIMESTAMP
      FROM stock_symbols s
      CROSS JOIN generate_series(1, 3)
      ON CONFLICT DO NOTHING
    `);
    result = await query('SELECT COUNT(*) as count FROM beta_validation');
    console.log(`   [OK] beta_validation: ${result.rows[0].count} rows\n`);

    // 9. Economic Calendar
    console.log('[9/16] Populating economic_calendar...');
    await query(`
      INSERT INTO economic_calendar (event_name, release_date, importance, forecast, actual, previous, created_at)
      SELECT
        CASE (RANDOM() * 10)::int
          WHEN 0 THEN 'Non-Farm Payroll'
          WHEN 1 THEN 'Unemployment Rate'
          WHEN 2 THEN 'CPI'
          WHEN 3 THEN 'PPI'
          WHEN 4 THEN 'GDP'
          WHEN 5 THEN 'Retail Sales'
          WHEN 6 THEN 'Fed Rate Decision'
          WHEN 7 THEN 'ISM Manufacturing'
          WHEN 8 THEN 'Durable Goods'
          ELSE 'Housing Starts'
        END,
        CURRENT_DATE - (RANDOM() * 365)::int,
        CASE (RANDOM() * 3)::int WHEN 0 THEN 'High' WHEN 1 THEN 'Medium' ELSE 'Low' END,
        ROUND((RANDOM() * 100)::numeric, 2),
        ROUND((RANDOM() * 100)::numeric, 2),
        ROUND((RANDOM() * 100)::numeric, 2),
        CURRENT_TIMESTAMP
      FROM generate_series(1, 200)
      ON CONFLICT DO NOTHING
    `);
    result = await query('SELECT COUNT(*) as count FROM economic_calendar');
    console.log(`   [OK] economic_calendar: ${result.rows[0].count} rows\n`);

    // 10. NAAIM
    console.log('[10/16] Populating naaim...');
    await query(`
      INSERT INTO naaim (date, bullish_pct, neutral_pct, bearish_pct, created_at)
      SELECT
        CURRENT_DATE - (RANDOM() * 365)::int,
        ROUND((RANDOM() * 100)::numeric, 2),
        ROUND((RANDOM() * 100)::numeric, 2),
        ROUND((RANDOM() * 100)::numeric, 2),
        CURRENT_TIMESTAMP
      FROM generate_series(1, 150)
      ON CONFLICT DO NOTHING
    `);
    result = await query('SELECT COUNT(*) as count FROM naaim');
    console.log(`   [OK] naaim: ${result.rows[0].count} rows\n`);

    // 11-13. ETF Buy/Sell Tables
    console.log('[11/16] Populating buy_sell_daily_etf...');
    await query(`
      INSERT INTO buy_sell_daily_etf (symbol, timeframe, date, signal, signal_triggered_date, strength, created_at)
      SELECT s.symbol, 'daily', CURRENT_DATE - (RANDOM() * 30)::int,
        CASE (RANDOM() * 2)::int WHEN 0 THEN 'Buy' WHEN 1 THEN 'Sell' ELSE 'Hold' END,
        CURRENT_DATE - (RANDOM() * 30)::int, ROUND((RANDOM() * 100)::numeric, 2), CURRENT_TIMESTAMP
      FROM etf_symbols s
      CROSS JOIN generate_series(1, 2)
      ON CONFLICT DO NOTHING
    `);
    result = await query('SELECT COUNT(*) as count FROM buy_sell_daily_etf');
    console.log(`   [OK] buy_sell_daily_etf: ${result.rows[0].count} rows\n`);

    console.log('[12/16] Populating buy_sell_weekly_etf...');
    await query(`
      INSERT INTO buy_sell_weekly_etf (symbol, timeframe, date, signal, signal_triggered_date, strength, created_at)
      SELECT s.symbol, 'weekly', CURRENT_DATE - (RANDOM() * 90)::int,
        CASE (RANDOM() * 2)::int WHEN 0 THEN 'Buy' WHEN 1 THEN 'Sell' ELSE 'Hold' END,
        CURRENT_DATE - (RANDOM() * 90)::int, ROUND((RANDOM() * 100)::numeric, 2), CURRENT_TIMESTAMP
      FROM etf_symbols s
      CROSS JOIN generate_series(1, 2)
      ON CONFLICT DO NOTHING
    `);
    result = await query('SELECT COUNT(*) as count FROM buy_sell_weekly_etf');
    console.log(`   [OK] buy_sell_weekly_etf: ${result.rows[0].count} rows\n`);

    console.log('[13/16] Populating buy_sell_monthly_etf...');
    await query(`
      INSERT INTO buy_sell_monthly_etf (symbol, timeframe, date, signal, signal_triggered_date, strength, created_at)
      SELECT s.symbol, 'monthly', CURRENT_DATE - (RANDOM() * 180)::int,
        CASE (RANDOM() * 2)::int WHEN 0 THEN 'Buy' WHEN 1 THEN 'Sell' ELSE 'Hold' END,
        CURRENT_DATE - (RANDOM() * 180)::int, ROUND((RANDOM() * 100)::numeric, 2), CURRENT_TIMESTAMP
      FROM etf_symbols s
      CROSS JOIN generate_series(1, 2)
      ON CONFLICT DO NOTHING
    `);
    result = await query('SELECT COUNT(*) as count FROM buy_sell_monthly_etf');
    console.log(`   [OK] buy_sell_monthly_etf: ${result.rows[0].count} rows\n`);

    // 14. ETF Price
    console.log('[14/16] Populating etf_price_daily...');
    await query(`
      INSERT INTO etf_price_daily (symbol, date, open, high, low, close, volume, created_at)
      SELECT s.symbol, CURRENT_DATE - (RANDOM() * 365)::int,
        ROUND((100 + RANDOM() * 100)::numeric, 2),
        ROUND((100 + RANDOM() * 100 + RANDOM() * 20)::numeric, 2),
        ROUND((100 + RANDOM() * 100 - RANDOM() * 20)::numeric, 2),
        ROUND((100 + RANDOM() * 100)::numeric, 2),
        (RANDOM() * 10000000)::int, CURRENT_TIMESTAMP
      FROM etf_symbols s
      CROSS JOIN generate_series(1, 5)
      ON CONFLICT DO NOTHING
    `);
    result = await query('SELECT COUNT(*) as count FROM etf_price_daily');
    console.log(`   [OK] etf_price_daily: ${result.rows[0].count} rows\n`);

    // 15. Expand Industry Ranking
    console.log('[15/16] Expanding industry_ranking...');
    await query(`
      INSERT INTO industry_ranking (industry, date_recorded, current_rank, rank_1w_ago, rank_4w_ago, rank_12w_ago, daily_strength_score, momentum_score, stock_count, trend, created_at)
      SELECT DISTINCT cp.industry, CURRENT_DATE - (RANDOM() * 365)::int,
        (RANDOM() * 101)::int + 1, (RANDOM() * 101)::int + 1, (RANDOM() * 101)::int + 1, (RANDOM() * 101)::int + 1,
        RANDOM() * 100, RANDOM() * 100, ((RANDOM() * 500) + 10)::int,
        CASE WHEN RANDOM() > 0.5 THEN 'UP' ELSE 'DOWN' END, CURRENT_TIMESTAMP
      FROM company_profile cp
      CROSS JOIN generate_series(1, 20)
      WHERE cp.industry IS NOT NULL
      ON CONFLICT DO NOTHING
    `);
    result = await query('SELECT COUNT(*) as count FROM industry_ranking');
    console.log(`   [OK] industry_ranking: ${result.rows[0].count} rows\n`);

    // 16. Last Updated
    console.log('[16/16] Populating last_updated...');
    await query('TRUNCATE TABLE last_updated');
    await query(`
      INSERT INTO last_updated (table_name, last_updated_at, created_at)
      VALUES
        ('stock_symbols', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
        ('price_daily', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
        ('technical_data_daily', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
        ('stock_scores', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
        ('company_profile', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    `);
    result = await query('SELECT COUNT(*) as count FROM last_updated');
    console.log(`   [OK] last_updated: ${result.rows[0].count} rows\n`);

    console.log('='.repeat(60));
    console.log('ALL REMAINING TABLES POPULATED SUCCESSFULLY');
    console.log('='.repeat(60));
    process.exit(0);
  } catch (err) {
    console.error('[ERROR]', err.message);
    process.exit(1);
  }
})();
