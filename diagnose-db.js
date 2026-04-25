const { Pool } = require('pg');
require('dotenv').config({ path: '.env.local' });

const pool = new Pool({
  host: process.env.DB_HOST,
  port: process.env.DB_PORT,
  user: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  database: process.env.DB_NAME,
});

async function diagnose() {
  try {
    console.log('\n📊 DATABASE DIAGNOSTIC REPORT\n');

    // Check which tables exist
    const tables = await pool.query(`
      SELECT table_name FROM information_schema.tables
      WHERE table_schema='public'
      ORDER BY table_name
    `);

    console.log(`✅ Found ${tables.rows.length} tables:\n`);

    // Get row counts for key tables
    const criticalTables = [
      'stock_symbols', 'price_daily', 'buy_sell_daily', 'buy_sell_weekly', 'buy_sell_monthly',
      'technical_data_daily', 'key_metrics', 'quality_metrics', 'growth_metrics',
      'earnings_estimates', 'earnings_history', 'annual_income_statement'
    ];

    for (const table of criticalTables) {
      try {
        const result = await pool.query(`SELECT COUNT(*) as count FROM ${table}`);
        const count = result.rows[0].count;
        const status = count > 0 ? '✅' : '⚠️';
        console.log(`${status} ${table}: ${count} rows`);
      } catch (err) {
        console.log(`❌ ${table}: TABLE NOT FOUND`);
      }
    }

    // Check columns in key_metrics
    console.log('\n📋 Columns in key_metrics:');
    try {
      const cols = await pool.query(`
        SELECT column_name FROM information_schema.columns
        WHERE table_name='key_metrics'
        ORDER BY column_name
      `);
      cols.rows.forEach(r => console.log(`  - ${r.column_name}`));
    } catch (err) {
      console.log('  (table does not exist)');
    }

    // Check for missing key_metrics columns that loaders expect
    console.log('\n🔍 Checking for missing columns loaders expect:');
    const expectedCols = ['return_on_equity_pct', 'return_on_assets_pct', 'revenue_growth_pct'];
    for (const col of expectedCols) {
      try {
        const result = await pool.query(`SELECT ${col} FROM key_metrics LIMIT 1`);
        console.log(`  ✅ ${col} exists`);
      } catch (err) {
        console.log(`  ❌ ${col} MISSING`);
      }
    }

    // Check annual_income_statement columns
    console.log('\n📋 Columns in annual_income_statement:');
    try {
      const cols = await pool.query(`
        SELECT column_name FROM information_schema.columns
        WHERE table_name='annual_income_statement'
        ORDER BY column_name
      `);
      if (cols.rows.length > 0) {
        cols.rows.slice(0, 20).forEach(r => console.log(`  - ${r.column_name}`));
        if (cols.rows.length > 20) console.log(`  ... and ${cols.rows.length - 20} more`);
      }
    } catch (err) {
      console.log('  (table does not exist)');
    }

    console.log('\n🚨 DATA COMPLETENESS ISSUES:\n');

    // Check buy_sell_daily coverage
    const bsd = await pool.query(`
      SELECT COUNT(DISTINCT ticker) as unique_tickers FROM buy_sell_daily
    `);
    console.log(`buy_sell_daily: ${bsd.rows[0].unique_tickers} stocks (should be 4969)`);

    // Check for etf tables
    const etfDaily = await pool.query(`
      SELECT COUNT(*) as count FROM etf_price_daily LIMIT 1
    `).catch(() => ({ rows: [{ count: 'NOT_FOUND' }] }));
    console.log(`etf_price_daily: ${etfDaily.rows[0].count} rows`);

    const etfWeekly = await pool.query(`
      SELECT COUNT(*) as count FROM etf_price_weekly LIMIT 1
    `).catch(() => ({ rows: [{ count: 'NOT_FOUND' }] }));
    console.log(`etf_price_weekly: ${etfWeekly.rows[0].count} rows`);

    console.log('\n');
    process.exit(0);
  } catch (err) {
    console.error('Error:', err.message);
    process.exit(1);
  }
}

diagnose();
