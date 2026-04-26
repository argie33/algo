#!/usr/bin/env node
/**
 * LIVE DATA QUALITY MONITOR
 * Shows real data coming through, catches nulls/errors immediately
 */

const { Pool } = require('pg');
const { execSync } = require('child_process');
const pool = new Pool({
  host: 'localhost',
  port: 5432,
  user: 'stocks',
  password: 'bed0elAn',
  database: 'stocks'
});

let lastCheck = {
  priceDaily: 0,
  timestamp: new Date()
};

async function checkData() {
  try {
    console.clear();
    console.log('╔════════════════════════════════════════════════════════════════╗');
    console.log('║ LIVE DATA QUALITY MONITOR - Real Data Verification             ║');
    console.log(`║ Updated: ${new Date().toLocaleTimeString()}                                         ║`);
    console.log('╚════════════════════════════════════════════════════════════════╝\n');

    // Check price_daily quality
    const priceDaily = await pool.query(`
      SELECT
        COUNT(*) as total,
        COUNT(DISTINCT symbol) as symbols,
        COUNT(DISTINCT DATE(date)) as days,
        SUM(CASE WHEN open IS NULL THEN 1 ELSE 0 END) as null_opens,
        SUM(CASE WHEN close IS NULL THEN 1 ELSE 0 END) as null_closes,
        SUM(CASE WHEN volume IS NULL OR volume = 0 THEN 1 ELSE 0 END) as null_volumes,
        MIN(close) as min_price,
        MAX(close) as max_price,
        ROUND(AVG(close)::numeric, 2) as avg_price
      FROM price_daily
    `);

    const pd = priceDaily.rows[0];
    const pdTotal = parseInt(pd.total);
    const newPD = pdTotal - lastCheck.priceDaily;

    console.log('📊 PRICE_DAILY (Historical prices)');
    console.log('─────────────────────────────────────────────────────────────');
    console.log(`  Total: ${pdTotal} records (↑ ${newPD} new)`);
    console.log(`  Coverage: ${pd.symbols} symbols × ${pd.days} days`);
    console.log(`  Price range: $${parseFloat(pd.min_price).toFixed(2)} - $${parseFloat(pd.max_price).toFixed(2)} (avg: $${pd.avg_price})`);

    // Check for data quality issues
    const nullIssues = [];
    if (pd.null_opens > 0) nullIssues.push(`${pd.null_opens} NULL opens`);
    if (pd.null_closes > 0) nullIssues.push(`${pd.null_closes} NULL closes`);
    if (pd.null_volumes > 0) nullIssues.push(`${pd.null_volumes} NULL/zero volumes`);

    if (nullIssues.length > 0) {
      console.log(`  ⚠️  Quality issues: ${nullIssues.join(', ')}`);
    } else if (pdTotal > 0) {
      console.log(`  ✅ Data quality: All prices valid (no nulls)`);
    }

    // Sample real data
    if (pdTotal > 0) {
      const sampleDaily = await pool.query(`
        SELECT symbol, date, open, close, volume
        FROM price_daily
        WHERE close IS NOT NULL AND volume > 0
        ORDER BY date DESC
        LIMIT 1
      `);

      if (sampleDaily.rows.length > 0) {
        const sample = sampleDaily.rows[0];
        const date = new Date(sample.date).toISOString().split('T')[0];
        console.log(`  📍 Latest real data: ${sample.symbol} on ${date}`);
        console.log(`     Open: $${parseFloat(sample.open).toFixed(2)} → Close: $${parseFloat(sample.close).toFixed(2)} | Vol: ${parseInt(sample.volume).toLocaleString()}`);
      }
    }

    lastCheck.priceDaily = pdTotal;

    // Check price_weekly
    const priceWeekly = await pool.query(`
      SELECT
        COUNT(*) as total
      FROM price_weekly
    `);

    const pw = priceWeekly.rows[0];
    console.log('\n📊 PRICE_WEEKLY (Aggregated)');
    console.log('─────────────────────────────────────────────────────────────');
    if (pw.total === '0' || pw.total === 0) {
      console.log(`  Status: ⏳ Empty (waiting for daily data to aggregate)`);
    } else {
      console.log(`  Total: ${pw.total} records ✅`);
    }

    // Check signals
    const signals = await pool.query(`
      SELECT
        (SELECT COUNT(*) FROM buy_sell_daily WHERE signal IN ('Buy', 'Sell')) as daily_buysell,
        (SELECT COUNT(*) FROM buy_sell_daily) as daily_total,
        (SELECT COUNT(*) FROM buy_sell_weekly WHERE signal IN ('Buy', 'Sell')) as weekly_buysell,
        (SELECT COUNT(*) FROM buy_sell_monthly WHERE signal IN ('Buy', 'Sell')) as monthly_buysell
    `);

    const sig = signals.rows[0];

    console.log('\n🎯 TRADING SIGNALS');
    console.log('─────────────────────────────────────────────────────────────');
    console.log(`  Daily: ${sig.daily_buysell} real signals (Buy/Sell) out of ${sig.daily_total} total`);

    if (sig.daily_buysell > 0) {
      const sampleSignal = await pool.query(`
        SELECT symbol, date, signal, buylevel
        FROM buy_sell_daily
        WHERE signal IN ('Buy', 'Sell')
        ORDER BY date DESC
        LIMIT 1
      `);
      if (sampleSignal.rows.length > 0) {
        const s = sampleSignal.rows[0];
        const date = new Date(s.date).toISOString().split('T')[0];
        console.log(`  📍 Latest: ${s.signal} for ${s.symbol} on ${date} (strength: ${s.buylevel})`);
        console.log(`  ✅ Real signals are generating`);
      }
    } else if (pdTotal > 10000) {
      console.log(`  ⚠️  No signals yet (checking why...)`);
    }

    console.log(`  Weekly: ${sig.weekly_buysell} signals`);
    console.log(`  Monthly: ${sig.monthly_buysell} signals`);

    // Phase progress
    try {
      const tail = execSync('tail -1 /tmp/historical_prices.log 2>/dev/null || echo ""', { encoding: 'utf8' });
      const match = tail.match(/batch (\d+)\/994/);
      if (match) {
        const batch = parseInt(match[1]);
        const pct = Math.round(batch * 100 / 994);
        console.log('\n🔄 PHASE 1 PROGRESS');
        console.log('─────────────────────────────────────────────────────────────');
        console.log(`  Batch ${batch}/994 (${pct}%)`);
        const bar = '█'.repeat(Math.floor(pct / 5)) + '░'.repeat(20 - Math.floor(pct / 5));
        console.log(`  [${bar}]`);
      }
    } catch (e) {
      // Silent
    }

    console.log('\n─────────────────────────────────────────────────────────────');
    console.log('Checking every 30 seconds. Ctrl+C to stop.\n');

  } catch (err) {
    console.error('ERROR:', err.message);
  }
}

// Check immediately, then every 30 seconds
checkData();
setInterval(checkData, 30000);

// Graceful shutdown
process.on('SIGINT', async () => {
  console.log('\n\nMonitor stopped.');
  await pool.end();
  process.exit(0);
});
