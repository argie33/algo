#!/usr/bin/env node
const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, 'webapp/lambda/.env.local') });
const { query } = require('./webapp/lambda/utils/database');

// Simple SMA calculation
function calculateSMA(prices, period) {
  if (prices.length < period) return null;
  const sum = prices.slice(-period).reduce((a, b) => a + b, 0);
  return sum / period;
}

// Simple ATR calculation
function calculateATR(highs, lows, closes, period = 14) {
  if (highs.length < 2 || lows.length < 2 || closes.length < 2) return null;

  let trueRanges = [];
  for (let i = 1; i < Math.min(highs.length, lows.length, closes.length); i++) {
    const h = highs[i];
    const l = lows[i];
    const pc = closes[i - 1];
    const tr = Math.max(h - l, Math.abs(h - pc), Math.abs(l - pc));
    trueRanges.push(tr);
  }

  if (trueRanges.length < period) return null;
  const sum = trueRanges.slice(-period).reduce((a, b) => a + b, 0);
  return sum / period;
}

// Simple ADX calculation (simplified)
function calculateADX(highs, lows, period = 14) {
  if (highs.length < period + 1 || lows.length < period + 1) return null;

  let upMoves = [], downMoves = [];
  for (let i = 1; i < highs.length; i++) {
    const upMove = highs[i] - highs[i-1];
    const downMove = lows[i-1] - lows[i];

    upMoves.push(upMove > downMove && upMove > 0 ? upMove : 0);
    downMoves.push(downMove > upMove && downMove > 0 ? downMove : 0);
  }

  if (upMoves.length < period) return null;

  const sumUp = upMoves.slice(-period).reduce((a, b) => a + b, 0);
  const sumDown = downMoves.slice(-period).reduce((a, b) => a + b, 0);

  const tr = Math.max(Math.abs(sumUp) + Math.abs(sumDown), 0.0001);
  const adx = (Math.abs(sumUp - sumDown) / tr) * 100;
  return adx > 0 ? adx : null;
}

async function calculateTechnicals() {
  console.log('\n📊 CALCULATING AND POPULATING ALL TECHNICAL INDICATORS\n');

  try {
    const stocks = await query('SELECT DISTINCT symbol FROM price_daily ORDER BY symbol LIMIT 300');
    const symbols = stocks.rows.map(r => r.symbol);

    let updated = 0;

    for (const symbol of symbols) {
      try {
        const priceResult = await query(`
          SELECT close, high, low, date FROM price_daily
          WHERE symbol = $1 ORDER BY date
        `, [symbol]);

        if (priceResult.rows.length < 30) continue;

        const closes = priceResult.rows.map(r => r.close);
        const highs = priceResult.rows.map(r => r.high);
        const lows = priceResult.rows.map(r => r.low);
        const latestRow = priceResult.rows[priceResult.rows.length - 1];

        // Calculate indicators
        const sma_20 = calculateSMA(closes, 20);
        const sma_50 = calculateSMA(closes, 50);
        const sma_200 = calculateSMA(closes, 200);
        const atr = calculateATR(highs, lows, closes, 14);
        const adx = calculateADX(highs, lows, 14);

        // Update database
        await query(`
          UPDATE technical_data_daily
          SET sma_20 = $1, sma_50 = $2, sma_200 = $3, atr = $4, adx = $5
          WHERE symbol = $6 AND date = $7
        `, [sma_20, sma_50, sma_200, atr, adx, symbol, latestRow.date]);

        updated++;
        if (updated % 50 === 0) {
          console.log(`  ✅ Processed ${updated} stocks...`);
        }
      } catch (e) {
        // Skip on error
      }
    }

    console.log(`\n✅ Populated ${updated} stocks with technical data`);

    // Verify data was populated
    const verify = await query(`
      SELECT COUNT(*) FILTER (WHERE adx IS NOT NULL) as adx_count,
             COUNT(*) FILTER (WHERE atr IS NOT NULL) as atr_count,
             COUNT(*) FILTER (WHERE sma_50 IS NOT NULL) as sma_count
      FROM technical_data_daily
    `);

    const counts = verify.rows[0];
    console.log('\n📊 VERIFICATION:');
    console.log(`  ADX values: ${counts.adx_count}`);
    console.log(`  ATR values: ${counts.atr_count}`);
    console.log(`  SMA_50 values: ${counts.sma_count}`);

  } catch(err) {
    console.error('❌ Error:', err.message);
  }

  process.exit(0);
}

calculateTechnicals();
