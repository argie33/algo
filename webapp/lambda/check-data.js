/* eslint-disable no-process-exit */
const { query } = require('./utils/database');

(async () => {
  try {
    process.env.DB_HOST = 'localhost';
    process.env.DB_PORT = '5432';
    process.env.DB_USER = 'stocks';
    process.env.DB_PASSWORD = 'bed0elAn';
    process.env.DB_NAME = 'stocks';
    process.env.DB_SSL = 'false';

    const tables = [
      'stock_symbols',
      'price_daily',
      'company_profile',
      'sector_ranking',
      'industry_ranking',
      'sector_performance',
      'industry_performance',
      'buy_sell_daily',
      'technical_indicators',
      'analyst_sentiment_analysis'
    ];

    console.log('\n📊 DATABASE STATUS:\n');
    for (const table of tables) {
      try {
        const result = await query(`SELECT COUNT(*) as count FROM ${table}`);
        const count = result?.rows?.[0]?.count || 0;
        console.log(`  ${table.padEnd(40)} ${count.toLocaleString()} rows`);
      } catch (e) {
        console.log(`  ${table.padEnd(40)} ❌ Table missing`);
      }
    }
    console.log('\n');
  } catch (err) {
    console.error('Error:', err.message);
    throw err;
  }
})().catch(e => {
  console.error('Fatal error:', e);
  process.exit(1);
});
