#!/usr/bin/env node

import pkg from 'pg';
const { Pool } = pkg;

const dbHost = process.env.DB_HOST || 'localhost';
const dbPort = process.env.DB_PORT || 5432;
const dbUser = process.env.DB_USER || 'stocks';
const dbPassword = process.env.DB_PASSWORD;
const dbName = process.env.DB_NAME || 'stocks';

if (!dbPassword) {
  console.error('ERROR: DB_PASSWORD environment variable is required');
  process.exit(1);
}

const DATABASE_URL = `postgresql://${dbUser}:${dbPassword}@${dbHost}:${dbPort}/${dbName}`;
const pool = new Pool({ connectionString: DATABASE_URL });

async function testAPI() {
  try {
    console.log("Testing covered-calls API query...\n");
    
    const query = `
      SELECT
        id, symbol, stock_price, strike, premium_pct,
        probability_of_profit, expected_annual_return, max_profit,
        entry_signal, entry_confidence, management_strategy,
        days_to_earnings, low_liquidity_warning, trend
      FROM covered_call_opportunities
      WHERE data_date = (SELECT MAX(data_date) FROM covered_call_opportunities)
      AND probability_of_profit >= 70
      AND premium_pct >= 1.5
      AND trend IN ('uptrend', 'sideways')
      AND (expiration_date - CURRENT_DATE) BETWEEN 30 AND 60
      ORDER BY premium_pct DESC
      LIMIT 50
    `;
    
    const result = await pool.query(query);
    console.log(`✅ Query successful!`);
    console.log(`   Found ${result.rows.length} opportunities\n`);
    
    // Show sample data
    if (result.rows.length > 0) {
      console.log("Sample top 3 opportunities:");
      console.log("═".repeat(100));
      result.rows.slice(0, 3).forEach((row, i) => {
        console.log(`\n${i+1}. ${row.symbol} - ${row.entry_signal}`);
        console.log(`   Strike: $${row.strike} | Premium: ${row.premium_pct.toFixed(2)}%`);
        console.log(`   PoP: ${row.probability_of_profit.toFixed(0)}% | Annual Return: ${row.expected_annual_return.toFixed(2)}%`);
        console.log(`   Management: ${row.management_strategy} | Confidence: ${row.entry_confidence}/10`);
      });
      console.log("\n" + "═".repeat(100));
    }
    
    await pool.end();
    
  } catch (error) {
    console.error("❌ Query Failed:", error.message);
    process.exit(1);
  }
}

testAPI();
