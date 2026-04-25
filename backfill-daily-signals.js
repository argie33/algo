#!/usr/bin/env node
/**
 * Backfill missing daily signals from weekly signals and price data
 * Fast backfill: Generate daily signals for all stocks using simple strategy
 */

const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, 'webapp/lambda/.env.local') });

const { query } = require('./webapp/lambda/utils/database');

async function backfillDailySignals() {
  console.log('\n🚀 BACKFILLING DAILY SIGNALS\n');

  try {
    // Get all stocks that have weekly signals but no daily signals
    const missingSignalsResult = await query(`
      SELECT DISTINCT s.symbol
      FROM stock_symbols s
      LEFT JOIN buy_sell_daily d ON s.symbol = d.symbol
      INNER JOIN buy_sell_weekly w ON s.symbol = w.symbol
      WHERE d.symbol IS NULL
      ORDER BY s.symbol
      LIMIT 1000
    `);

    const stocksNeedingSignals = missingSignalsResult.rows.map(r => r.symbol);
    console.log(`📊 Found ${stocksNeedingSignals.length} stocks needing daily signals\n`);

    if (stocksNeedingSignals.length === 0) {
      console.log('✅ All stocks already have daily signals');
      process.exit(0);
    }

    let inserted = 0;
    let skipped = 0;

    // Batch process symbols
    const batchSize = 50;
    for (let i = 0; i < stocksNeedingSignals.length; i += batchSize) {
      const batch = stocksNeedingSignals.slice(i, i + batchSize);
      const placeholders = batch.map((_, idx) => `$${idx + 1}`).join(',');

      // For each stock, get latest weekly signal and use it as daily
      const signalsResult = await query(`
        SELECT DISTINCT ON (symbol)
          symbol,
          signal,
          date,
          strength,
          signal_strength
        FROM buy_sell_weekly
        WHERE symbol IN (${placeholders})
          AND signal IN ('Buy', 'Sell')
        ORDER BY symbol, date DESC
      `, batch);

      // Insert as daily signals
      for (const row of signalsResult.rows) {
        try {
          // Use weekly signal date, but mark it as daily
          await query(`
            INSERT INTO buy_sell_daily
              (symbol, signal, date, signal_triggered_date, strength, signal_strength, timeframe, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, 'daily', NOW())
            ON CONFLICT DO NOTHING
          `, [
            row.symbol,
            row.signal,
            row.date,
            row.date,
            row.strength || 50,
            row.signal_strength || 50
          ]);
          inserted++;
        } catch (err) {
          console.error(`❌ Failed to insert ${row.symbol}:`, err.message.substring(0, 100));
          skipped++;
        }
      }

      const progress = Math.min(i + batchSize, stocksNeedingSignals.length);
      console.log(`  Progress: ${progress}/${stocksNeedingSignals.length} stocks processed (${inserted} inserted)`);
    }

    console.log(`\n✅ Backfill complete!`);
    console.log(`   Inserted: ${inserted} signals`);
    console.log(`   Skipped: ${skipped} signals`);

    // Check final count
    const finalCount = await query(`
      SELECT COUNT(*) as total FROM buy_sell_daily
      WHERE signal IN ('Buy', 'Sell')
    `);

    console.log(`\n📊 Final daily signal count: ${finalCount.rows[0].total.toLocaleString()}`);

  } catch (err) {
    console.error('❌ Error:', err.message);
    process.exit(1);
  }

  process.exit(0);
}

backfillDailySignals();
