#!/usr/bin/env node

const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, 'webapp/lambda/.env.local') });

const { query } = require('./webapp/lambda/utils/database');

async function checkData() {
  console.log('\n=== DATABASE DATA CHECK ===\n');

  const tables = [
    { name: 'stock_symbols', query: 'SELECT COUNT(*) as count FROM stock_symbols' },
    { name: 'price_daily', query: 'SELECT COUNT(*) as count FROM price_daily' },
    { name: 'buy_sell_daily', query: 'SELECT COUNT(*) as count FROM buy_sell_daily' },
    { name: 'buy_sell_weekly', query: 'SELECT COUNT(*) as count FROM buy_sell_weekly' },
    { name: 'buy_sell_monthly', query: 'SELECT COUNT(*) as count FROM buy_sell_monthly' },
    { name: 'technical_data_daily', query: 'SELECT COUNT(*) as count FROM technical_data_daily' },
    { name: 'earnings_estimates', query: 'SELECT COUNT(*) as count FROM earnings_estimates' },
  ];

  for (const table of tables) {
    try {
      const result = await query(table.query);
      const count = parseInt(result.rows[0]?.count || 0);
      const status = count > 0 ? '✅' : '⚠️';
      console.log(`${status} ${table.name}: ${count.toLocaleString()} records`);
    } catch (err) {
      console.log(`❌ ${table.name}: Error - ${err.message.substring(0, 50)}`);
    }
  }

  // Check sample signals
  console.log('\n=== SAMPLE SIGNALS ===\n');
  try {
    const result = await query(`
      SELECT symbol, signal, date, timeframe
      FROM buy_sell_daily
      WHERE signal IN ('Buy', 'Sell')
      LIMIT 5
    `);
    if (result.rows.length > 0) {
      console.log('✅ Sample signals found:');
      result.rows.forEach(row => {
        console.log(`  ${row.symbol} - ${row.signal} on ${row.date}`);
      });
    } else {
      console.log('⚠️ No signals found in buy_sell_daily table');
    }
  } catch (err) {
    console.log(`❌ Error querying signals: ${err.message}`);
  }

  console.log('\n');
  process.exit(0);
}

checkData().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
