#!/usr/bin/env node
/**
 * Direct test of weekly query without server - tests the query directly
 */

const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, 'webapp/lambda/.env.local') });

const { query } = require('./webapp/lambda/utils/database');

async function test() {
  console.log('\n🧪 TESTING WEEKLY QUERY DIRECTLY\n');

  try {
    // Run the exact query that should work for weekly
    const result = await query(`
      SELECT
        bsd.id, bsd.symbol, bsd.timeframe, bsd.date, bsd.signal_triggered_date,
        bsd.signal, bsd.strength, NULL::float as signal_strength,
        p.open, p.high, p.low, p.close, p.volume
      FROM buy_sell_weekly bsd
      LEFT JOIN price_weekly p ON bsd.symbol = p.symbol
        AND DATE(p.date) = DATE(bsd.date)
      WHERE bsd.signal IN ('Buy', 'Sell')
      LIMIT 5
    `);

    console.log(`✅ Query succeeded!`);
    console.log(`   Rows returned: ${result.rows.length}`);
    console.log(`   First row fields:`, Object.keys(result.rows[0] || {}).join(', '));
    if (result.rows.length > 0) {
      console.log(`   First signal: ${result.rows[0].symbol} - ${result.rows[0].signal}`);
    }
  } catch (err) {
    console.log(`❌ Query failed:`, err.message);
  }

  process.exit(0);
}

test();
