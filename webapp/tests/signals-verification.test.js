/**
 * Trading Signals Verification Test
 * Verifies all data is present and correctly formatted
 */

const { test, expect } = require('@playwright/test');
const { execSync } = require('child_process');

test.describe('Trading Signals - Complete Data Verification', () => {
  
  test('✅ Daily table has signal data', async () => {
    const result = execSync(
      `psql -h localhost -U postgres -d stocks -c "SELECT COUNT(*) as cnt FROM buy_sell_daily WHERE signal IN ('Buy','Sell')" -t`,
      { encoding: 'utf8', env: { ...process.env, PGPASSWORD: 'password' } }
    );
    const count = parseInt(result.trim());
    console.log(`\n✅ Daily signals: ${count} records`);
    expect(count).toBeGreaterThan(0);
  });

  test('✅ Weekly has 100% market_stage populated', async () => {
    const result = execSync(
      `psql -h localhost -U postgres -d stocks -c "SELECT ROUND(100.0 * COUNT(CASE WHEN market_stage IS NOT NULL THEN 1 END) / COUNT(*), 1) as pct FROM buy_sell_weekly WHERE signal IN ('Buy','Sell')" -t`,
      { encoding: 'utf8', env: { ...process.env, PGPASSWORD: 'password' } }
    );
    const pct = result.trim();
    console.log(`✅ Weekly market_stage: ${pct}% populated`);
    expect(pct).toBe('100.0');
  });

  test('✅ Weekly has 100% quality_score populated', async () => {
    const result = execSync(
      `psql -h localhost -U postgres -d stocks -c "SELECT ROUND(100.0 * COUNT(CASE WHEN entry_quality_score IS NOT NULL THEN 1 END) / COUNT(*), 1) as pct FROM buy_sell_weekly WHERE signal IN ('Buy','Sell')" -t`,
      { encoding: 'utf8', env: { ...process.env, PGPASSWORD: 'password' } }
    );
    const pct = result.trim();
    console.log(`✅ Weekly quality_score: ${pct}% populated`);
    expect(pct).toBe('100.0');
  });

  test('✅ Monthly has 100% market_stage populated', async () => {
    const result = execSync(
      `psql -h localhost -U postgres -d stocks -c "SELECT ROUND(100.0 * COUNT(CASE WHEN market_stage IS NOT NULL THEN 1 END) / COUNT(*), 1) as pct FROM buy_sell_monthly WHERE signal IN ('Buy','Sell')" -t`,
      { encoding: 'utf8', env: { ...process.env, PGPASSWORD: 'password' } }
    );
    const pct = result.trim();
    console.log(`✅ Monthly market_stage: ${pct}% populated`);
    expect(pct).toBe('100.0');
  });

  test('✅ Monthly has 100% quality_score populated', async () => {
    const result = execSync(
      `psql -h localhost -U postgres -d stocks -c "SELECT ROUND(100.0 * COUNT(CASE WHEN entry_quality_score IS NOT NULL THEN 1 END) / COUNT(*), 1) as pct FROM buy_sell_monthly WHERE signal IN ('Buy','Sell')" -t`,
      { encoding: 'utf8', env: { ...process.env, PGPASSWORD: 'password' } }
    );
    const pct = result.trim();
    console.log(`✅ Monthly quality_score: ${pct}% populated`);
    expect(pct).toBe('100.0');
  });

  test('✅ API handler has correct field mappings', async () => {
    const fs = require('fs');
    const content = fs.readFileSync('/home/stocks/algo/webapp/lambda/routes/signals.js', 'utf8');
    expect(content).toContain('market_stage');
    expect(content).toContain('entry_quality_score');
    expect(content).toContain('bsd.market_stage');
    console.log('✅ signals.js includes market_stage and entry_quality_score mappings');
  });

  test('✅ Frontend uses dynamic API config', async () => {
    const fs = require('fs');
    const content = fs.readFileSync('/home/stocks/algo/webapp/frontend/src/components/SignalPerformanceTracker.jsx', 'utf8');
    expect(content).toContain('getApiConfig');
    expect(content).not.toContain('http://localhost:3001');
    console.log('✅ SignalPerformanceTracker uses getApiConfig() for API URL');
  });

  test('✅ Weekly sample data shows all fields', async () => {
    const result = execSync(
      `psql -h localhost -U postgres -d stocks -c "SELECT symbol, date, signal, market_stage, entry_quality_score, strength FROM buy_sell_weekly WHERE signal IN ('Buy','Sell') LIMIT 1" -t`,
      { encoding: 'utf8', env: { ...process.env, PGPASSWORD: 'password' } }
    );
    console.log('\n📊 WEEKLY SAMPLE:\n' + result);
    expect(result).toContain('Stage');
    expect(result).toContain('|');
  });

  test('✅ Monthly sample data shows all fields', async () => {
    const result = execSync(
      `psql -h localhost -U postgres -d stocks -c "SELECT symbol, date, signal, market_stage, entry_quality_score, strength FROM buy_sell_monthly WHERE signal IN ('Buy','Sell') LIMIT 1" -t`,
      { encoding: 'utf8', env: { ...process.env, PGPASSWORD: 'password' } }
    );
    console.log('\n📊 MONTHLY SAMPLE:\n' + result);
    expect(result).toContain('Stage');
    expect(result).toContain('|');
  });

});
