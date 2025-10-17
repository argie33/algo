const { query } = require('./utils/database');

async function populateHistoricalData() {
  try {
    console.log('Populating historical sector and industry rankings...');
    
    // Add historical sector rankings
    const historicalDates = [
      { days: 0, label: 'today' },
      { days: 7, label: '1_week_ago' },
      { days: 21, label: '3_weeks_ago' },
      { days: 56, label: '8_weeks_ago' }
    ];
    
    const sectors = [
      ['XLK', 'Technology', 1, 2.0],
      ['XLV', 'Healthcare', 2, 4.0],
      ['XLF', 'Financials', 10, -4.1],
      ['XLY', 'Consumer Discretionary', 8, -3.2],
      ['XLP', 'Consumer Staples', 6, -0.4],
      ['XLE', 'Energy', 11, -4.1],
      ['XLI', 'Industrials', 5, -0.3],
      ['XLB', 'Materials', 7, -2.6],
      ['XLU', 'Utilities', 1, 9.6],
      ['XLRE', 'Real Estate', 4, 0.1],
      ['XLC', 'Communication Services', 9, -3.7]
    ];
    
    // Insert historical sector data
    for (const date of historicalDates) {
      const fetchDate = new Date();
      fetchDate.setDate(fetchDate.getDate() - date.days);
      
      for (let i = 0; i < sectors.length; i++) {
        const [symbol, sector_name, rank, perf] = sectors[i];
        const adjustedRank = (rank + i) % 11 + 1; // Vary ranks slightly
        
        await query(`
          INSERT INTO sector_performance 
          (symbol, sector_name, price, change, change_percent, volume, momentum, money_flow, rsi, performance_1d, performance_5d, performance_20d, sector_rank, fetched_at)
          VALUES ($1, $2, 100.0, 0.5, 0.5, 1000000, 'Strong', 'Inflow', 55.0, 0.5, 1.5, $3, $4, $5)
          ON CONFLICT DO NOTHING
        `, [symbol, sector_name, perf, adjustedRank, fetchDate]);
      }
    }
    
    console.log('✅ Inserted historical sector rankings');
    
    // Insert historical industry data
    const industries = [
      ['Technology', 'Software', 1, 2.0],
      ['Healthcare', 'Pharmaceuticals', 2, 2.5],
      ['Financials', 'Banks', 3, -2.0],
      ['Industrials', 'Machinery', 4, 1.0],
      ['Consumer Cyclical', 'Retailers', 5, -2.5]
    ];
    
    for (const date of historicalDates) {
      const fetchDate = new Date();
      fetchDate.setDate(fetchDate.getDate() - date.days);
      
      for (let i = 0; i < industries.length; i++) {
        const [sector, industry, rank, perf] = industries[i];
        const adjustedRank = (rank + i) % 5 + 1;
        
        await query(`
          INSERT INTO industry_performance
          (sector, industry, industry_key, stock_count, momentum, trend, overall_rank, sector_rank, performance_1d, performance_5d, performance_20d, fetched_at)
          VALUES ($1, $2, $3, 50, 'Strong', 'Uptrend', $4, $4, 0.5, 1.0, $5, $6)
          ON CONFLICT DO NOTHING
        `, [sector, industry, industry.toUpperCase().substring(0,4), adjustedRank, perf, fetchDate]);
      }
    }
    
    console.log('✅ Inserted historical industry rankings');
    console.log('✅ Historical data population complete');
    process.exit(0);
  } catch (error) {
    console.error('❌ Error:', error.message);
    process.exit(1);
  }
}

populateHistoricalData();
