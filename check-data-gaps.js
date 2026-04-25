const { Pool } = require('pg');
require('dotenv').config({ path: '.env.local' });

const pool = new Pool({
  host: process.env.DB_HOST,
  port: process.env.DB_PORT,
  user: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  database: process.env.DB_NAME,
});

async function check() {
  try {
    console.log('\n📊 DATA COMPLETENESS REPORT\n');

    // Key table counts
    const tables = [
      'stock_symbols',
      'price_daily',
      'buy_sell_daily',
      'buy_sell_weekly',
      'buy_sell_monthly',
      'technical_data_daily',
      'earnings_history',
      'key_metrics',
      'quality_metrics'
    ];

    for (const table of tables) {
      const result = await pool.query(`SELECT COUNT(*) as count FROM ${table}`);
      const count = result.rows[0].count;
      console.log(`${table.padEnd(25)} : ${count}`);
    }

    // Check buy_sell_daily coverage
    const bsd = await pool.query(`SELECT COUNT(DISTINCT symbol) as count FROM buy_sell_daily`);
    const all_stocks = await pool.query(`SELECT COUNT(*) as count FROM stock_symbols`);
    const coverage = (bsd.rows[0].count / all_stocks.rows[0].count * 100).toFixed(1);
    console.log(`\n⚠️  buy_sell_daily coverage: ${coverage}% (${bsd.rows[0].count}/${all_stocks.rows[0].count} stocks)`);

    // Check for NULL signals
    const nulls = await pool.query(`SELECT COUNT(*) as count FROM buy_sell_daily WHERE signal IS NULL`);
    console.log(`⚠️  buy_sell_daily with NULL signals: ${nulls.rows[0].count}`);

    // Check price_daily coverage
    const prices = await pool.query(`SELECT COUNT(DISTINCT symbol) as count FROM price_daily`);
    console.log(`\n✅ price_daily symbols: ${prices.rows[0].count}/${all_stocks.rows[0].count}`);

    // Check key_metrics coverage
    const km = await pool.query(`SELECT COUNT(DISTINCT symbol) as count FROM key_metrics`);
    console.log(`✅ key_metrics symbols: ${km.rows[0].count}/${all_stocks.rows[0].count}`);

    process.exit(0);
  } catch (err) {
    console.error('Error:', err.message);
    process.exit(1);
  }
}

check();
