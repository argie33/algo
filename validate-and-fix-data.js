#!/usr/bin/env node
/**
 * Data Validation & Health Check
 *
 * This script:
 * 1. Validates data in all critical tables
 * 2. Reports what's missing
 * 3. Checks for schema mismatches
 * 4. Provides API readiness report
 */

const { query } = require('./webapp/lambda/utils/database');

process.env.DB_HOST = 'localhost';
process.env.DB_PORT = '5432';
process.env.DB_USER = 'stocks';
process.env.DB_PASSWORD = 'bed0elAn';
process.env.DB_NAME = 'stocks';
process.env.DB_SSL = 'false';

const TABLES_EXPECTED = {
  'company_profile': { expected_rows: 4969, purpose: 'Stock company info from yfinance' },
  'key_metrics': { expected_rows: 4969, purpose: 'Stock valuation metrics (PE, yield, etc.)' },
  'stock_symbols': { expected_rows: 4969, purpose: 'Master list of stocks' },
  'earnings_estimates': { expected_rows: 5000, purpose: 'Analyst earnings forecasts' },
  'earnings_history': { expected_rows: 19999, purpose: 'Actual reported earnings' },
  'price_daily': { expected_rows: 300000, purpose: 'Daily OHLCV price data' },
  'institutional_positioning': { expected_rows: 50000, purpose: 'Institutional ownership data' },
  'insider_transactions': { expected_rows: 10000, purpose: 'Insider buy/sell activity' },
  'sector_ranking': { expected_rows: 3500, purpose: 'Sector performance rankings' },
  'industry_ranking': { expected_rows: 2000, purpose: 'Industry performance rankings' },
  'technical_data_daily': { expected_rows: 25000, purpose: 'Daily technical indicators' },
  'stock_scores': { expected_rows: 4969, purpose: 'Composite quality/value/growth scores' },
};

const CRITICAL_TABLES = [
  'company_profile',
  'key_metrics',
  'earnings_estimates',
  'earnings_history',
  'price_daily',
];

async function checkTable(tableName) {
  try {
    const result = await query(
      `SELECT COUNT(*) as cnt, MIN(created_at) as oldest, MAX(updated_at) as newest
       FROM ${tableName}`,
      []
    );

    const count = result.rows?.[0]?.cnt || 0;
    const oldest = result.rows?.[0]?.oldest;
    const newest = result.rows?.[0]?.newest;

    return { count, oldest, newest, error: null };
  } catch (err) {
    return { count: 0, oldest: null, newest: null, error: err.message };
  }
}

async function validateSchema() {
  console.log('\n📋 SCHEMA VALIDATION\n');

  const result = await query(`
    SELECT
      tablename,
      CAST(reltuples AS INT) as estimated_rows
    FROM pg_tables
    JOIN pg_class ON relname = tablename
    WHERE schemaname = 'public'
    ORDER BY reltuples DESC
  `, []);

  const tables = {};
  result?.rows?.forEach(r => {
    tables[r.tablename] = r.estimated_rows;
  });

  console.log(`Total tables: ${Object.keys(tables).length}\n`);

  console.log('🟢 CRITICAL TABLES:');
  for (const table of CRITICAL_TABLES) {
    const rows = tables[table] || 0;
    const expected = TABLES_EXPECTED[table]?.expected_rows || 0;
    const status = rows > 0 ? '✅' : '❌';
    console.log(`  ${status} ${table.padEnd(30)} ${rows.toString().padStart(10)} / ${expected} rows`);
  }

  console.log('\n🟡 IMPORTANT TABLES:');
  const others = Object.keys(TABLES_EXPECTED).filter(t => !CRITICAL_TABLES.includes(t));
  for (const table of others) {
    const rows = tables[table] || 0;
    const expected = TABLES_EXPECTED[table].expected_rows;
    const status = rows > 0 ? '✅' : '⚠️';
    console.log(`  ${status} ${table.padEnd(30)} ${rows.toString().padStart(10)} / ${expected} rows`);
  }

  console.log('\n🔴 EMPTY/PROBLEMATIC TABLES:');
  const problemTables = Object.entries(tables).filter(([name, count]) => count <= 0);
  if (problemTables.length === 0) {
    console.log('  None found - all expected tables have data!');
  } else {
    problemTables.forEach(([name, count]) => {
      console.log(`  ❌ ${name.padEnd(30)} ${count} rows`);
    });
  }
}

async function checkDataQuality() {
  console.log('\n📊 DATA QUALITY CHECK\n');

  // Check company_profile completeness
  console.log('Company Profile Coverage:');
  try {
    const result = await query(`
      SELECT
        COUNT(*) as total,
        COUNT(CASE WHEN sector IS NOT NULL THEN 1 END) as with_sector,
        COUNT(CASE WHEN industry IS NOT NULL THEN 1 END) as with_industry,
        COUNT(CASE WHEN market_cap IS NULL THEN 1 END) as null_market_cap
      FROM company_profile
    `, []);

    const row = result.rows?.[0];
    if (row) {
      const sectorPct = ((row.with_sector / row.total) * 100).toFixed(1);
      const industryPct = ((row.with_industry / row.total) * 100).toFixed(1);
      console.log(`  Total: ${row.total} | Sector: ${sectorPct}% | Industry: ${industryPct}%`);
    }
  } catch (e) {
    console.log(`  ❌ Error: ${e.message}`);
  }

  // Check earnings coverage
  console.log('\nEarnings Data Coverage:');
  try {
    const result = await query(`
      SELECT
        COUNT(*) as estimates_total,
        COUNT(DISTINCT symbol) as symbols_with_estimates,
        (SELECT COUNT(*) FROM earnings_history) as history_total,
        (SELECT COUNT(DISTINCT symbol) FROM earnings_history) as history_symbols
      FROM earnings_estimates
    `, []);

    const row = result.rows?.[0];
    if (row) {
      console.log(`  Estimates: ${row.estimates_total} rows (${row.symbols_with_estimates} symbols)`);
      console.log(`  History: ${row.history_total} rows (${row.history_symbols} symbols)`);
    }
  } catch (e) {
    console.log(`  ❌ Error: ${e.message}`);
  }

  // Check price data
  console.log('\nPrice Data Coverage:');
  try {
    const result = await query(`
      SELECT
        COUNT(*) as total_records,
        COUNT(DISTINCT symbol) as unique_symbols,
        MIN(date) as earliest_date,
        MAX(date) as latest_date,
        COUNT(CASE WHEN volume IS NULL THEN 1 END) as null_volumes
      FROM price_daily
    `, []);

    const row = result.rows?.[0];
    if (row) {
      console.log(`  Total: ${row.total_records} records (${row.unique_symbols} symbols)`);
      console.log(`  Date range: ${row.earliest_date} to ${row.latest_date}`);
      console.log(`  Missing volumes: ${row.null_volumes}`);
    }
  } catch (e) {
    console.log(`  ❌ Error: ${e.message}`);
  }
}

async function reportAPIs() {
  console.log('\n🚀 API READINESS REPORT\n');

  const apis = [
    { name: 'Earnings', tables: ['earnings_estimates', 'earnings_history'] },
    { name: 'Stocks', tables: ['company_profile', 'key_metrics', 'price_daily'] },
    { name: 'Stocks Scores', tables: ['stock_scores'] },
    { name: 'Technical', tables: ['technical_data_daily', 'price_daily'] },
    { name: 'Institutional', tables: ['institutional_positioning'] },
    { name: 'Insider', tables: ['insider_transactions'] },
    { name: 'Sectors', tables: ['sector_ranking', 'company_profile'] },
    { name: 'Industries', tables: ['industry_ranking', 'company_profile'] },
  ];

  for (const api of apis) {
    const result = await query(`
      SELECT tablename, CAST(reltuples AS INT) as estimated_rows
      FROM pg_tables
      JOIN pg_class ON relname = tablename
      WHERE schemaname = 'public' AND tablename = ANY($1)
    `, [api.tables]);

    const status = result?.rows?.every(r => r.estimated_rows > 0) ? '✅' : '❌';
    const dataStatus = result?.rows?.map(r => `${r.tablename}(${r.estimated_rows})`).join(', ');
    console.log(`  ${status} ${api.name.padEnd(20)} ${dataStatus || 'MISSING'}`);
  }
}

async function main() {
  try {
    console.log('🔍 DATABASE VALIDATION REPORT - ' + new Date().toISOString());
    console.log('='.repeat(80));

    await validateSchema();
    await checkDataQuality();
    await reportAPIs();

    console.log('\n' + '='.repeat(80));
    console.log('✅ Validation complete!');
    console.log('\nNEXT STEPS:');
    console.log('1. Run: python loaddailycompanydata.py  (populates company/earnings data)');
    console.log('2. Run: python loadstockscores.py       (populates stock scores)');
    console.log('3. Run this script again to verify data');

    process.exit(0);
  } catch (err) {
    console.error('❌ Fatal error:', err.message);
    process.exit(1);
  }
}

main();
