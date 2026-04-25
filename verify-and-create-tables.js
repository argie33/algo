#!/usr/bin/env node
const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, 'webapp/lambda/.env.local') });
const { query } = require('./webapp/lambda/utils/database');

const requiredTables = [
  'stock_symbols',
  'price_daily',
  'price_weekly',
  'price_monthly',
  'technical_data_daily',
  'technical_data_weekly',
  'technical_data_monthly',
  'buy_sell_daily',
  'buy_sell_weekly',
  'buy_sell_monthly',
  'buy_sell_daily_etf',
  'buy_sell_weekly_etf',
  'buy_sell_monthly_etf',
  'etf_symbols',
  'sector_ranking',
  'industry_ranking',
];

async function verifyTables() {
  console.log('\n📊 VERIFYING DATABASE TABLES\n');

  try {
    const result = await query(`
      SELECT table_name FROM information_schema.tables
      WHERE table_schema = 'public'
      ORDER BY table_name
    `);

    const existingTables = new Set(result.rows.map(r => r.table_name));

    console.log('📋 CHECKING REQUIRED TABLES:');
    const missing = [];
    const present = [];

    requiredTables.forEach(table => {
      if (existingTables.has(table)) {
        console.log(`  ✅ ${table}`);
        present.push(table);
      } else {
        console.log(`  ❌ ${table} - MISSING`);
        missing.push(table);
      }
    });

    console.log(`\n📊 SUMMARY:`);
    console.log(`  Present: ${present.length}/${requiredTables.length}`);
    console.log(`  Missing: ${missing.length}`);

    if (missing.length > 0) {
      console.log(`\n⚠️ MISSING TABLES:`);
      missing.forEach(t => console.log(`  - ${t}`));
      console.log(`\n💡 These tables need to be created or populated with data`);
    } else {
      console.log(`\n✅ All required tables exist!`);
    }

  } catch(err) {
    console.error('❌ Error:', err.message);
  }

  process.exit(0);
}

verifyTables();
