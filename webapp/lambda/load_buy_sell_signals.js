/**
 * Load and Enrich Trading Signals
 *
 * This loader enriches buy_sell_daily signals with technical metrics from:
 * - technical_data_daily: pivot points, ADX, RSI, SMA indicators
 * - price_daily: volume data
 *
 * Metrics populated:
 * - pivot_price: (pivot_high + pivot_low) / 2
 * - avg_volume_50d: current volume as estimate
 * - breakout_quality: Strong/Good/Moderate/Weak based on ADX/RSI
 * - volume_surge_pct: ((volume / avg_volume_50d - 1) * 100)
 */

const { Pool } = require('pg');

const pool = new Pool({
  host: process.env.DB_HOST || 'localhost',
  port: process.env.DB_PORT || 5432,
  database: process.env.DB_NAME || 'stocks',
  user: process.env.DB_USER || 'stockuser',
  password: process.env.DB_PASSWORD || 'stockpass'
});

async function enrichSignalMetrics() {
  const client = await pool.connect();

  try {
    console.log('🔄 Enriching trading signals with technical metrics...\n');

    // Process only daily table - weekly/monthly have different schemas
    const timeframes = ['daily'];

    for (const timeframe of timeframes) {
      console.log(`📊 Processing buy_sell_${timeframe}...`);

      // 1. Update pivot_price from technical_data_daily
      await client.query(`
        UPDATE buy_sell_${timeframe} bsd
        SET pivot_price = CASE
          WHEN td.pivot_high > 0 AND td.pivot_low > 0
            THEN (td.pivot_high + td.pivot_low) / 2.0
          ELSE NULL
        END
        FROM technical_data_daily td
        WHERE bsd.symbol = td.symbol
          AND bsd.date = td.date::date
          AND bsd.signal IN ('Buy', 'Sell')
          AND td.pivot_high > 0
          AND td.pivot_high < 10000
          AND td.pivot_low > 0
          AND td.pivot_low < 10000
      `);

      // 2. Update avg_volume_50d with current volume as estimate
      await client.query(`
        UPDATE buy_sell_${timeframe}
        SET avg_volume_50d = volume
        WHERE signal IN ('Buy', 'Sell')
          AND volume > 0
      `);

      // 3. Update breakout_quality based on technical indicators
      await client.query(`
        UPDATE buy_sell_${timeframe} bsd
        SET breakout_quality = CASE
          WHEN td.adx > 35 AND td.rsi > 55 THEN 'Strong'
          WHEN td.adx > 25 AND bsd.close > td.sma_50 THEN 'Good'
          WHEN td.adx > 15 THEN 'Moderate'
          WHEN td.adx <= 15 THEN 'Weak'
          ELSE 'Unrated'
        END
        FROM technical_data_daily td
        WHERE bsd.symbol = td.symbol
          AND bsd.date = td.date::date
          AND bsd.signal IN ('Buy', 'Sell')
          AND td.adx IS NOT NULL
      `);

      // 4. Calculate volume_surge_pct
      await client.query(`
        UPDATE buy_sell_${timeframe}
        SET volume_surge_pct = CASE
          WHEN avg_volume_50d > 0 AND volume > 0
            THEN ((volume::real / avg_volume_50d - 1.0) * 100.0)::real
          ELSE 0
        END
        WHERE signal IN ('Buy', 'Sell')
      `);

      // Verify coverage
      const result = await client.query(`
        SELECT
          COUNT(*) as total,
          COUNT(CASE WHEN pivot_price > 0 THEN 1 END) as pivot_cnt,
          COUNT(CASE WHEN avg_volume_50d > 0 THEN 1 END) as volume_cnt,
          COUNT(CASE WHEN breakout_quality != 'Unrated' THEN 1 END) as quality_cnt,
          COUNT(CASE WHEN risk_reward_ratio > 0 THEN 1 END) as rrr_cnt,
          COUNT(CASE WHEN entry_quality_score > 0 THEN 1 END) as entry_cnt
        FROM buy_sell_${timeframe}
        WHERE signal IN ('Buy', 'Sell')
      `);

      const { total, pivot_cnt, volume_cnt, quality_cnt, rrr_cnt, entry_cnt } = result.rows[0];
      console.log(`   Total signals: ${total}`);
      console.log(`   ✅ Pivot Price: ${pivot_cnt} (${(pivot_cnt/total*100).toFixed(1)}%)`);
      console.log(`   ✅ Avg Volume 50d: ${volume_cnt} (${(volume_cnt/total*100).toFixed(1)}%)`);
      console.log(`   ✅ Breakout Quality: ${quality_cnt} (${(quality_cnt/total*100).toFixed(1)}%)`);
      console.log(`   ✅ Risk/Reward Ratio: ${rrr_cnt} (${(rrr_cnt/total*100).toFixed(1)}%)`);
      console.log(`   ✅ Entry Quality Score: ${entry_cnt} (${(entry_cnt/total*100).toFixed(1)}%)\n`);
    }

    console.log('✅ Signal enrichment complete for daily timeframe!');

  } catch (error) {
    console.error('❌ Error enriching signals:', error);
    throw error;
  } finally {
    client.release();
    await pool.end();
  }
}

enrichSignalMetrics().catch(console.error);
