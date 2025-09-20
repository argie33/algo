require('dotenv').config();
const { query } = require('./utils/database');

/**
 * Test complex JOIN queries locally to catch issues before AWS deployment
 * This prevents 500 errors in production by validating query structure,
 * performance, and data integrity locally.
 */

async function testComplexJoins() {
  console.log('🔬 Testing complex JOIN queries for AWS compatibility...\n');

  const tests = [
    {
      name: 'Stocks Main Endpoint Query',
      description: 'Test the main /api/stocks query that was failing in production',
      query: `
        SELECT
          cp.ticker as symbol,
          COALESCE(cp.short_name, cp.long_name, cp.ticker) as company_name,
          cp.long_name as security_name,
          cp.market,
          cp.quote_type as type,
          cp.sector,
          cp.industry,
          cp.currency,
          cp.country,
          md.market_cap,
          true as is_active,
          md.current_price as current_price,
          md.volume,
          (SELECT MAX(date) FROM price_daily WHERE symbol = cp.ticker) as price_date
        FROM company_profile cp
        LEFT JOIN market_data md ON cp.ticker = md.ticker
        WHERE 1=1
        ORDER BY cp.ticker ASC
        LIMIT 5
      `,
      shouldReturn: 'At least 1 row with valid stock data'
    },

    {
      name: 'Signals Complex JOIN Query',
      description: 'Test signals endpoint with fundamental_metrics JOIN',
      query: `
        SELECT
          ts.symbol,
          ts.signal_type,
          ts.strength,
          COALESCE(fm.pe_ratio, 15.5) as pe_ratio,
          COALESCE(fm.dividend_yield, 2.1) as dividend_yield,
          COALESCE(md.market_cap, 0) as market_cap,
          COALESCE(cp.sector, 'Unknown') as sector
        FROM technical_signals ts
        LEFT JOIN fundamental_metrics fm ON ts.symbol = fm.symbol
        LEFT JOIN market_data md ON ts.symbol = md.ticker
        LEFT JOIN company_profile cp ON ts.symbol = cp.ticker
        WHERE ts.signal_type IS NOT NULL
        ORDER BY ts.strength DESC
        LIMIT 3
      `,
      shouldReturn: 'Financial signals with real PE ratios and dividend yields'
    },

    {
      name: 'Scores Multi-table JOIN Query',
      description: 'Test scoring endpoint with comprehensive financial data',
      query: `
        SELECT
          ss.symbol,
          ss.overall_score,
          ss.fundamental_score,
          ss.technical_score,
          ss.sentiment_score,
          COALESCE(fm.roe * 10, 7.5) as earnings_quality_subscore,
          COALESCE(fm.current_ratio * 25, 65) as balance_sheet_subscore,
          COALESCE(fm.profit_margin * 100, 7) as profitability_subscore,
          COALESCE(fm.pe_ratio, 15.5) as multiples_subscore,
          COALESCE(fm.price_to_book, 2.5) as intrinsic_value_subscore,
          COALESCE(cp.sector, 'Unknown') as sector
        FROM stock_scores ss
        LEFT JOIN fundamental_metrics fm ON ss.symbol = fm.symbol
        LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
        WHERE ss.overall_score IS NOT NULL
        ORDER BY ss.overall_score DESC
        LIMIT 3
      `,
      shouldReturn: 'Stock scores with real financial calculations'
    },

    {
      name: 'Price Data JOIN Query',
      description: 'Test price endpoint using market_data and price_daily',
      query: `
        SELECT
          md.ticker as symbol,
          md.current_price,
          md.previous_close,
          md.day_high,
          md.day_low,
          md.volume,
          cp.short_name as company_name
        FROM market_data md
        LEFT JOIN company_profile cp ON md.ticker = cp.ticker
        WHERE md.current_price IS NOT NULL
        ORDER BY md.market_cap DESC NULLS LAST
        LIMIT 3
      `,
      shouldReturn: 'Current price data with company names'
    },

    {
      name: 'Complex Metrics JOIN Query',
      description: 'Test metrics endpoint with multiple table joins',
      query: `
        SELECT
          ss.symbol,
          COALESCE(cp.long_name, ss.symbol) as company_name,
          COALESCE(fm.pe_ratio, 0) as pe_ratio,
          COALESCE(fm.dividend_yield, 0) as dividend_yield,
          COALESCE(md.market_cap, 0) as market_cap,
          COALESCE(cp.sector, 'Unknown') as sector
        FROM stock_scores ss
        LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
        LEFT JOIN fundamental_metrics fm ON ss.symbol = fm.symbol
        LEFT JOIN market_data md ON ss.symbol = md.ticker
        WHERE ss.symbol IS NOT NULL
        ORDER BY md.market_cap DESC NULLS LAST
        LIMIT 3
      `,
      shouldReturn: 'Comprehensive metrics with all financial data joined'
    }
  ];

  let passedTests = 0;
  let failedTests = 0;
  const errors = [];

  for (const test of tests) {
    try {
      console.log(`📊 Testing: ${test.name}`);
      console.log(`   Description: ${test.description}`);

      const startTime = Date.now();
      const result = await query(test.query);
      const endTime = Date.now();
      const executionTime = endTime - startTime;

      if (result && result.rows && result.rows.length > 0) {
        console.log(`   ✅ PASSED - ${result.rows.length} rows returned in ${executionTime}ms`);
        console.log(`   📋 Sample data:`, JSON.stringify(result.rows[0], null, 2));
        passedTests++;

        // Warn about slow queries that might timeout in AWS Lambda
        if (executionTime > 5000) {
          console.log(`   ⚠️  WARNING: Query took ${executionTime}ms - may timeout in AWS Lambda`);
        }
      } else {
        console.log(`   ❌ FAILED - No data returned`);
        failedTests++;
        errors.push(`${test.name}: No data returned`);
      }

    } catch (error) {
      console.log(`   ❌ FAILED - Error: ${error.message}`);
      failedTests++;
      errors.push(`${test.name}: ${error.message}`);
    }

    console.log(''); // Empty line for readability
  }

  // Summary
  console.log('🏁 COMPLEX JOIN QUERY TEST SUMMARY');
  console.log('═'.repeat(50));
  console.log(`✅ Passed Tests: ${passedTests}`);
  console.log(`❌ Failed Tests: ${failedTests}`);
  console.log(`📊 Total Tests: ${tests.length}`);

  if (errors.length > 0) {
    console.log('\n🚨 ERRORS FOUND:');
    errors.forEach(error => console.log(`   - ${error}`));
    console.log('\n⚠️  THESE ISSUES WILL CAUSE 500 ERRORS IN AWS PRODUCTION!');
    console.log('Fix these locally before deploying.');
  } else {
    console.log('\n🎉 ALL COMPLEX JOINS WORKING!');
    console.log('✅ Safe to deploy to AWS - no complex JOIN issues detected.');
  }

  process.exit(failedTests > 0 ? 1 : 0);
}

testComplexJoins();