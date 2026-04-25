#!/usr/bin/env node
const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, 'webapp/lambda/.env.local') });
const { query } = require('./webapp/lambda/utils/database');

function calculateRSI(closes, period = 14) {
  if (closes.length < period + 1) return null;
  let gains = 0, losses = 0;
  for (let i = 1; i < period + 1; i++) {
    const diff = closes[i] - closes[i - 1];
    if (diff > 0) gains += diff;
    else losses += Math.abs(diff);
  }
  let avgGain = gains / period;
  let avgLoss = losses / period;
  for (let i = period + 1; i < closes.length; i++) {
    const diff = closes[i] - closes[i - 1];
    if (diff > 0) {
      avgGain = (avgGain * (period - 1) + diff) / period;
      avgLoss = (avgLoss * (period - 1)) / period;
    } else {
      avgGain = (avgGain * (period - 1)) / period;
      avgLoss = (avgLoss * (period - 1) + Math.abs(diff)) / period;
    }
  }
  const rs = avgGain / avgLoss;
  return 100 - (100 / (1 + rs));
}

function calculateSMA(prices, period) {
  if (prices.length < period) return null;
  const sum = prices.slice(-period).reduce((a, b) => a + b, 0);
  return sum / period;
}

function calculateATR(highs, lows, closes, period = 14) {
  if (highs.length < period) return null;
  let tr = 0;
  for (let i = 1; i < period; i++) {
    const h = highs[i];
    const l = lows[i];
    const c = closes[i - 1];
    tr += Math.max(h - l, Math.abs(h - c), Math.abs(l - c));
  }
  return tr / period;
}

function calculateEMA(prices, period) {
  if (prices.length < period) return null;
  const k = 2 / (period + 1);
  let ema = prices.slice(0, period).reduce((a, b) => a + b, 0) / period;
  for (let i = period; i < prices.length; i++) {
    ema = prices[i] * k + ema * (1 - k);
  }
  return ema;
}

function calculateADX(highs, lows, closes, period = 14) {
  if (highs.length < period * 2) return null;

  let plusDM = 0, minusDM = 0, tr = 0;
  for (let i = 1; i < period; i++) {
    const upMove = highs[i] - highs[i-1];
    const downMove = lows[i-1] - lows[i];

    if (upMove > downMove && upMove > 0) plusDM += upMove;
    else plusDM += 0;

    if (downMove > upMove && downMove > 0) minusDM += downMove;
    else minusDM += 0;

    const h = highs[i], l = lows[i], c = closes[i-1];
    tr += Math.max(h - l, Math.abs(h - c), Math.abs(l - c));
  }

  let plusDI = (plusDM / tr) * 100 || 0;
  let minusDI = (minusDM / tr) * 100 || 0;
  let dx = Math.abs(plusDI - minusDI) / (plusDI + minusDI) * 100 || 0;
  return dx > 0 ? dx : null;
}

async function populateTechnicals() {
  console.log('\n🔧 POPULATING TECHNICAL INDICATORS\n');

  try {
    const stocksResult = await query('SELECT symbol FROM stock_symbols ORDER BY symbol LIMIT 200');
    const stocks = stocksResult.rows.map(r => r.symbol);

    let updated = 0;

    for (const symbol of stocks) {
      try {
        const pricesResult = await query(`
          SELECT close, high, low, date
          FROM price_daily
          WHERE symbol = $1
          ORDER BY date
          LIMIT 250
        `, [symbol]);

        if (pricesResult.rows.length > 50) {
          const closes = pricesResult.rows.map(r => r.close);
          const highs = pricesResult.rows.map(r => r.high);
          const lows = pricesResult.rows.map(r => r.low);

          const rsi = calculateRSI(closes);
          const sma20 = calculateSMA(closes, 20);
          const sma50 = calculateSMA(closes, 50);
          const sma200 = calculateSMA(closes, 200);
          const atr = calculateATR(highs, lows, closes);
          const ema12 = calculateEMA(closes, 12);
          const ema26 = calculateEMA(closes, 26);
          const adx = calculateADX(highs, lows, closes);

          const latestDate = pricesResult.rows[pricesResult.rows.length - 1].date;

          await query(`
            INSERT INTO technical_data_daily (symbol, date, rsi, sma_20, sma_50, sma_200, atr, adx, ema_12, ema_26)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (symbol, date) DO UPDATE SET
              rsi = $3,
              sma_20 = $4,
              sma_50 = $5,
              sma_200 = $6,
              atr = $7,
              adx = $8,
              ema_12 = $9,
              ema_26 = $10
          `, [symbol, latestDate, rsi, sma20, sma50, sma200, atr, adx, ema12, ema26]);

          updated++;
        }
      } catch(e) {
        // Skip on error
      }

      if (updated % 20 === 0 && updated > 0) {
        console.log(`  ✅ Updated ${updated} stocks...`);
      }
    }

    console.log(`\n✅ Populated technical data for ${updated} stocks`);

  } catch(err) {
    console.error('❌ Error:', err.message);
  }

  process.exit(0);
}

populateTechnicals();
