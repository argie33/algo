#!/usr/bin/env node

const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, 'webapp/lambda/.env.local') });

const { query } = require('./webapp/lambda/utils/database');

async function testSignalsAPI() {
  console.log('\n=== TESTING SIGNALS API QUERY ===\n');

  try {
    // Simulate what the /api/signals/stocks endpoint does
    const timeframe = 'daily';
    const limit = 50;
    const page = 1;
    const offset = (page - 1) * limit;

    const tableName = 'buy_sell_daily';

    // Build the query (from signals.js lines ~117-145)
    let sql = `
      SELECT
        id,
        symbol,
        signal,
        date,
        signal_triggered_date,
        strength,
        timeframe
      FROM ${tableName}
      WHERE signal IN ('Buy', 'Sell')
        AND date >= '2019-01-01'
      ORDER BY date DESC, symbol ASC
      LIMIT $1 OFFSET $2
    `;

    console.log('Running query...');
    const result = await query(sql, [limit, offset]);

    console.log(`\nQuery returned ${result.rows.length} rows`);

    if (result.rows.length > 0) {
      console.log('\nFirst 3 signals:');
      result.rows.slice(0, 3).forEach((row, i) => {
        console.log(`\n  ${i+1}. ${row.symbol}`);
        console.log(`     Signal: ${row.signal}`);
        console.log(`     Date: ${row.date}`);
        console.log(`     Strength: ${row.strength}`);
        console.log(`     All fields:`, Object.keys(row));
      });
    }

    // Now get total count
    const countSql = `
      SELECT COUNT(*) as total FROM ${tableName}
      WHERE signal IN ('Buy', 'Sell')
        AND date >= '2019-01-01'
    `;

    console.log('\n\nGetting total count...');
    const countResult = await query(countSql, []);
    const total = parseInt(countResult.rows[0].total || 0);

    console.log(`Total signals: ${total}`);
    console.log(`Total pages (limit=${limit}): ${Math.ceil(total / limit)}`);

    // Simulate the response
    console.log('\n\n=== SIMULATED API RESPONSE ===\n');
    const response = {
      success: true,
      items: result.rows.slice(0, 3), // Just first 3 for demo
      pagination: {
        page: page,
        limit: limit,
        total: total,
        totalPages: Math.ceil(total / limit),
        hasNext: offset + limit < total,
        hasPrev: offset > 0
      },
      timestamp: new Date().toISOString()
    };

    console.log(JSON.stringify(response, null, 2));

  } catch (err) {
    console.error('❌ Error:', err.message);
    console.error(err.stack);
  }

  process.exit(0);
}

testSignalsAPI();
