const { query } = require('../utils/database');

// Simple test script to check data availability
async function testDataRetrieval() {
  try {
    console.log('Testing data retrieval for Agilent (A)...');
    
    // Test company_profile table
    const companyProfileQuery = `
      SELECT ticker, short_name, long_name, business_summary, employee_count, website_url, country
      FROM company_profile 
      WHERE ticker = 'A'
      LIMIT 1
    `;
    
    const companyResult = await query(companyProfileQuery);
    console.log('Company Profile Data:', companyResult.rows[0]);
    
    // Test market_data table
    const marketDataQuery = `
      SELECT ticker, current_price, previous_close, day_low, day_high, volume, market_cap
      FROM market_data 
      WHERE ticker = 'A'
      LIMIT 1
    `;
    
    const marketResult = await query(marketDataQuery);
    console.log('Market Data:', marketResult.rows[0]);
    
    // Test key_metrics table
    const keyMetricsQuery = `
      SELECT ticker, trailing_pe, peg_ratio, price_to_book, eps_trailing, profit_margin_pct
      FROM key_metrics 
      WHERE ticker = 'A'
      LIMIT 1
    `;
    
    const metricsResult = await query(keyMetricsQuery);
    console.log('Key Metrics Data:', metricsResult.rows[0]);
    
    // Test stock_symbols table
    const stockSymbolsQuery = `
      SELECT symbol, security_name, exchange
      FROM stock_symbols 
      WHERE symbol = 'A'
      LIMIT 1
    `;
    
    const symbolResult = await query(stockSymbolsQuery);
    console.log('Stock Symbols Data:', symbolResult.rows[0]);
    
    // Test the actual JOIN query used in the API
    const fullQuery = `
      SELECT 
        ss.symbol,
        ss.security_name,
        cp.short_name,
        cp.long_name,
        cp.business_summary,
        cp.employee_count,
        cp.website_url,
        cp.country,
        md.current_price,
        md.previous_close,
        md.day_low,
        md.day_high,
        md.volume,
        md.average_volume,
        km.trailing_pe,
        km.peg_ratio,
        km.price_to_book,
        km.eps_trailing,
        km.profit_margin_pct
      FROM stock_symbols ss
      LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
      LEFT JOIN market_data md ON ss.symbol = md.ticker
      LEFT JOIN key_metrics km ON ss.symbol = km.ticker
      WHERE ss.symbol = 'A'
      LIMIT 1
    `;
    
    const fullResult = await query(fullQuery);
    console.log('Full JOIN Query Result:', fullResult.rows[0]);
    
    // Check table existence and row counts
    const tableChecks = [
      'stock_symbols',
      'company_profile', 
      'market_data',
      'key_metrics'
    ];
    
    for (const table of tableChecks) {
      try {
        const countResult = await query(`SELECT COUNT(*) as count FROM ${table}`);
        console.log(`${table}: ${countResult.rows[0].count} rows`);
        
        // Get sample of column names
        const columnResult = await query(`
          SELECT column_name 
          FROM information_schema.columns 
          WHERE table_name = '${table}' 
          ORDER BY ordinal_position
        `);
        console.log(`${table} columns:`, columnResult.rows.map(r => r.column_name).join(', '));
        
      } catch (err) {
        console.log(`${table}: ERROR - ${err.message}`);
      }
    }
    
  } catch (error) {
    console.error('Test failed:', error);
  }
}

module.exports = { testDataRetrieval };

// Run if executed directly
if (require.main === module) {
  testDataRetrieval().then(() => {
    console.log('Test completed');
    process.exit(0);
  }).catch(err => {
    console.error('Test error:', err);
    process.exit(1);
  });
}
