#!/usr/bin/env node
/**
 * Data Coverage Audit Script
 *
 * Checks current database for data coverage across all tables.
 * Compares against expected 515 S&P 500 stocks.
 *
 * Usage: node check-data-coverage.js
 */

const { Pool } = require('pg');
const path = require('path');
require('dotenv').config({ path: '.env.local' });

const pool = new Pool({
  host: process.env.DB_HOST || 'localhost',
  port: process.env.DB_PORT || 5432,
  user: process.env.DB_USER || 'stocks',
  password: process.env.DB_PASSWORD,
  database: process.env.DB_NAME || 'stocks',
});

const EXPECTED_STOCKS = 515;

async function checkTable(tableName, distinctColumn = 'symbol') {
  try {
    const result = await pool.query(
      `SELECT COUNT(DISTINCT ${distinctColumn}) as count FROM ${tableName}`
    );
    const count = result.rows[0].count || 0;
    const coverage = ((count / EXPECTED_STOCKS) * 100).toFixed(1);

    return {
      table: tableName,
      count: parseInt(count),
      coverage: parseFloat(coverage),
      status: coverage >= 95 ? '✅ GOOD' : coverage >= 50 ? '⚠️ PARTIAL' : '❌ CRITICAL'
    };
  } catch (err) {
    return {
      table: tableName,
      count: 0,
      coverage: 0,
      status: '❌ ERROR',
      error: err.message
    };
  }
}

async function main() {
  console.log('\n📊 STOCK ANALYTICS PLATFORM - DATA COVERAGE AUDIT');
  console.log('=' .repeat(60));
  console.log(`Expected coverage: ${EXPECTED_STOCKS} stocks\n`);

  try {
    // Test connection
    await pool.query('SELECT 1');
    console.log('✅ Database connected\n');

    // Group tables by category
    const categories = {
      'PRICE DATA': [
        'price_daily', 'price_weekly', 'price_monthly',
        'latest_price_daily', 'latest_price_weekly', 'latest_price_monthly'
      ],
      'TECHNICAL SIGNALS': [
        'buy_sell_daily', 'buy_sell_weekly', 'buy_sell_monthly'
      ],
      'COMPANY DATA': [
        'company_profile', 'key_metrics',
        'institutional_positioning', 'positioning_metrics',
        'insider_transactions', 'insider_roster'
      ],
      'EARNINGS DATA': [
        'earnings_estimates', 'earnings_history', 'earnings_revisions'
      ],
      'ANALYST DATA': [
        'analyst_sentiment_analysis', 'analyst_upgrade_downgrade'
      ],
      'OPTIONS DATA': [
        'options_chains'
      ],
      'FINANCIAL STATEMENTS': [
        'annual_income_statement', 'annual_balance_sheet', 'annual_cash_flow',
        'quarterly_income_statement', 'quarterly_balance_sheet', 'quarterly_cash_flow',
        'ttm_income_statement', 'ttm_cash_flow'
      ],
      'RANKINGS': [
        'sector_ranking', 'industry_ranking'
      ],
      'SCORES': [
        'stock_scores'
      ],
      'OTHER': [
        'factor_metrics', 'market_data', 'relative_performance', 'seasonality_data'
      ]
    };

    let totalCritical = 0;
    let totalPartial = 0;
    let totalGood = 0;

    for (const [category, tables] of Object.entries(categories)) {
      console.log(`\n${category}`);
      console.log('-' .repeat(60));

      for (const table of tables) {
        const result = await checkTable(table);

        if (result.error) {
          console.log(`${result.status} ${result.table.padEnd(35)} (${result.error})`);
        } else {
          const bar = '█'.repeat(Math.ceil(result.coverage / 5));
          const barEmpty = '░'.repeat(20 - Math.ceil(result.coverage / 5));
          console.log(
            `${result.status} ${result.table.padEnd(35)} ${result.count.toString().padStart(3)}/${EXPECTED_STOCKS} [${bar}${barEmpty}] ${result.coverage}%`
          );

          if (result.status === '✅ GOOD') totalGood++;
          else if (result.status === '⚠️ PARTIAL') totalPartial++;
          else if (result.status === '❌ CRITICAL') totalCritical++;
        }
      }
    }

    // Summary
    console.log('\n' + '=' .repeat(60));
    console.log('SUMMARY');
    console.log('=' .repeat(60));
    console.log(`✅ Excellent (≥95%):  ${totalGood} tables`);
    console.log(`⚠️  Partial (50-95%):   ${totalPartial} tables`);
    console.log(`❌ Critical (<50%):    ${totalCritical} tables`);

    console.log('\nRECOMMENDATIONS:');
    if (totalCritical > 0) {
      console.log('1. Run the following loaders to fix critical gaps:');
      console.log('   bash run-all-loaders.sh');
      console.log('   (This will take 30-60 minutes)');
    }
    if (totalPartial > 0) {
      console.log('2. Some data sources (yfinance) have limited coverage');
      console.log('   Consider alternative data providers for:');
      console.log('   - Earnings estimates (FactSet, Seeking Alpha)');
      console.log('   - Options chains (Polygon.io, IEX Cloud)');
      console.log('   - Analyst data (premium services)');
    }
    console.log('3. Once loaders run, check /tmp/*.log for issues');

    console.log('\n');

  } catch (err) {
    console.error('❌ Database connection failed:');
    console.error(`   ${err.message}`);
    console.error('\nMake sure:');
    console.error('  1. PostgreSQL is running');
    console.error('  2. .env.local has correct DB_HOST, DB_USER, DB_PASSWORD');
    console.error('  3. Database "stocks" exists: createdb -U stocks stocks');
  } finally {
    await pool.end();
  }
}

main().catch(console.error);
