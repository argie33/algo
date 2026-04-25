#!/usr/bin/env node

const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, 'webapp/lambda/.env.local') });

const { query } = require('./webapp/lambda/utils/database');

async function analyzeSignalData() {
  console.log('\n=== SIGNAL DATA COVERAGE ANALYSIS ===\n');

  try {
    // Get sample signals with all their columns
    const sampleResult = await query(`
      SELECT *
      FROM buy_sell_daily
      WHERE signal IN ('Buy', 'Sell')
      LIMIT 10
    `);

    if (sampleResult.rows.length === 0) {
      console.log('❌ No signals found');
      process.exit(0);
    }

    const firstSignal = sampleResult.rows[0];
    const columnNames = Object.keys(firstSignal);

    console.log(`📊 Total columns in buy_sell_daily: ${columnNames.length}`);
    console.log(`\n📋 Sample signal (${firstSignal.symbol} - ${firstSignal.signal}):\n`);

    // Analyze which columns have data vs NULL
    const populated = [];
    const empty = [];

    columnNames.forEach(col => {
      let nullCount = 0;
      sampleResult.rows.forEach(row => {
        if (row[col] === null || row[col] === undefined) nullCount++;
      });

      const populationRate = ((10 - nullCount) / 10 * 100).toFixed(0);

      if (nullCount === 10) {
        empty.push(col);
      } else if (nullCount === 0) {
        populated.push(`✅ ${col.padEnd(30)} (100%)`);
      } else {
        populated.push(`⚠️  ${col.padEnd(30)} (${populationRate}%)`);
      }
    });

    console.log('POPULATED COLUMNS:\n');
    populated.forEach(p => console.log('  ' + p));

    if (empty.length > 0) {
      console.log(`\nEMPTY COLUMNS (${empty.length}):\n`);
      empty.slice(0, 10).forEach(col => {
        console.log(`  ❌ ${col}`);
      });
      if (empty.length > 10) {
        console.log(`  ... and ${empty.length - 10} more`);
      }
    }

    // Count signals by coverage level
    console.log('\n\n=== SIGNAL QUALITY METRICS ===\n');

    const qualityResult = await query(`
      SELECT
        symbol,
        signal,
        COUNT(*) as total_records,
        SUM(CASE WHEN strength IS NOT NULL THEN 1 ELSE 0 END) as has_strength,
        SUM(CASE WHEN rsi IS NOT NULL THEN 1 ELSE 0 END) as has_rsi,
        SUM(CASE WHEN adx IS NOT NULL THEN 1 ELSE 0 END) as has_adx,
        SUM(CASE WHEN entry_quality_score IS NOT NULL THEN 1 ELSE 0 END) as has_entry_quality
      FROM buy_sell_daily
      WHERE signal IN ('Buy', 'Sell')
      GROUP BY symbol, signal
      ORDER BY total_records DESC
      LIMIT 5
    `);

    console.log('Top 5 stocks with most signals:');
    qualityResult.rows.forEach((row, idx) => {
      const strengthRate = ((row.has_strength / row.total_records) * 100).toFixed(0);
      const rsiRate = ((row.has_rsi / row.total_records) * 100).toFixed(0);
      console.log(`\n${idx+1}. ${row.symbol} (${row.signal}): ${row.total_records} signals`);
      console.log(`   Strength: ${strengthRate}% | RSI: ${rsiRate}%`);
    });

  } catch (err) {
    console.error('❌ Error:', err.message);
  }

  process.exit(0);
}

analyzeSignalData();
