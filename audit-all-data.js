#!/usr/bin/env node

const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, 'webapp/lambda/.env.local') });

const { query } = require('./webapp/lambda/utils/database');

async function auditData() {
  console.log('\n📊 COMPREHENSIVE DATA AUDIT\n');
  console.log('='.repeat(80));

  try {
    // Check all critical tables
    const tables = [
      { name: 'stock_symbols', type: 'reference' },
      { name: 'price_daily', type: 'price' },
      { name: 'price_weekly', type: 'price' },
      { name: 'price_monthly', type: 'price' },
      { name: 'technical_data_daily', type: 'technical' },
      { name: 'buy_sell_daily', type: 'signals' },
      { name: 'buy_sell_weekly', type: 'signals' },
      { name: 'buy_sell_monthly', type: 'signals' },
      { name: 'earnings_estimates', type: 'fundamental' },
      { name: 'earnings_history', type: 'fundamental' },
    ];

    console.log('\n📋 TABLE RECORD COUNTS:\n');

    let totalRecords = 0;
    const tableStats = {};

    for (const table of tables) {
      try {
        const result = await query(`SELECT COUNT(*) as count FROM ${table.name}`);
        const count = parseInt(result.rows[0]?.count || 0);
        tableStats[table.name] = { count, type: table.type };
        totalRecords += count;

        const status = count > 0 ? '✅' : '⚠️';
        console.log(`${status} ${table.name.padEnd(25)} ${count.toString().padStart(10)} records [${table.type}]`);
      } catch (err) {
        console.log(`❌ ${table.name.padEnd(25)} ERROR - ${err.message.substring(0, 50)}`);
      }
    }

    console.log('\n' + '='.repeat(80));
    console.log(`📈 TOTAL: ${totalRecords.toLocaleString()} records across all tables\n`);

    // Data coverage analysis
    console.log('📊 DATA COVERAGE ANALYSIS:\n');

    const stockCount = tableStats['stock_symbols']?.count || 0;

    if (stockCount > 0) {
      const coverageData = [
        { table: 'price_daily', expected: stockCount * 250 },
        { table: 'price_weekly', expected: stockCount * 50 },
        { table: 'price_monthly', expected: stockCount * 12 },
        { table: 'technical_data_daily', expected: stockCount * 50 },
        { table: 'buy_sell_daily', expected: stockCount },
        { table: 'buy_sell_weekly', expected: stockCount },
        { table: 'buy_sell_monthly', expected: stockCount },
      ];

      console.log(`Based on ${stockCount.toLocaleString()} stocks:\n`);

      for (const data of coverageData) {
        const actual = tableStats[data.table]?.count || 0;
        const coverage = Math.round((actual / data.expected) * 100);
        const status = coverage >= 80 ? '✅' : coverage >= 50 ? '⚠️' : '❌';
        console.log(
          `${status} ${data.table.padEnd(25)} ${actual.toString().padStart(10)} / ${data.expected.toString().padStart(10)} (${coverage}%)`
        );
      }
    }

    // Check for NULL values in signal tables
    console.log('\n' + '='.repeat(80));
    console.log('\n🔍 SIGNAL TABLE COLUMN COVERAGE:\n');

    for (const timeframe of ['daily', 'weekly', 'monthly']) {
      const tableName = `buy_sell_${timeframe}`;
      try {
        const result = await query(`
          SELECT
            COUNT(*) as total,
            SUM(CASE WHEN signal_triggered_date IS NOT NULL THEN 1 ELSE 0 END) as has_trigger_date,
            SUM(CASE WHEN strength IS NOT NULL THEN 1 ELSE 0 END) as has_strength
          FROM ${tableName}
          WHERE signal IN ('Buy', 'Sell')
        `);

        const row = result.rows[0];
        const total = parseInt(row.total || 0);
        const triggerRate = total > 0 ? Math.round((row.has_trigger_date / total) * 100) : 0;
        const strengthRate = total > 0 ? Math.round((row.has_strength / total) * 100) : 0;

        console.log(`${timeframe.toUpperCase()} (${total} signals):`);
        console.log(`  • signal_triggered_date: ${triggerRate}%`);
        console.log(`  • strength: ${strengthRate}%`);
        console.log('');
      } catch (err) {
        console.log(`❌ ${timeframe}: ${err.message}\n`);
      }
    }

    // Missing data analysis
    console.log('='.repeat(80));
    console.log('\n⚠️ MISSING DATA SUMMARY:\n');

    const missing = [];

    // Price data
    if ((tableStats['price_daily']?.count || 0) === 0) {
      missing.push('❌ price_daily - NO DATA LOADED');
    }
    if ((tableStats['price_weekly']?.count || 0) === 0) {
      missing.push('❌ price_weekly - NO DATA LOADED');
    }
    if ((tableStats['price_monthly']?.count || 0) === 0) {
      missing.push('❌ price_monthly - NO DATA LOADED');
    }

    // Technical data
    if ((tableStats['technical_data_daily']?.count || 0) < stockCount * 10) {
      missing.push('⚠️ technical_data_daily - SPARSE (less than 10% coverage)');
    }

    // Fundamental data
    if ((tableStats['earnings_estimates']?.count || 0) < stockCount * 0.05) {
      missing.push('⚠️ earnings_estimates - SPARSE (less than 5% coverage)');
    }

    if (missing.length === 0) {
      console.log('✅ All critical tables are populated\n');
    } else {
      missing.forEach(m => console.log(m));
      console.log('');
    }

  } catch (err) {
    console.error('❌ Error:', err.message);
  }

  console.log('='.repeat(80) + '\n');
  process.exit(0);
}

auditData();
