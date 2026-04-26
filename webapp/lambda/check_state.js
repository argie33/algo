const { query } = require("./utils/database");

async function checkState() {
  try {
    const priceResult = await query(`
      SELECT 
        COUNT(*) as total,
        COUNT(DISTINCT symbol) as symbols,
        MIN(date) as min_date,
        MAX(date) as max_date
      FROM price_daily
    `);
    
    const technicalResult = await query(`
      SELECT 
        COUNT(*) as total,
        COUNT(DISTINCT symbol) as symbols,
        MIN(date) as min_date,
        MAX(date) as max_date
      FROM technical_data_daily
    `);
    
    const signalResult = await query(`
      SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN signal = 'Buy' THEN 1 ELSE 0 END) as buys,
        SUM(CASE WHEN signal = 'Sell' THEN 1 ELSE 0 END) as sells,
        SUM(CASE WHEN signal = 'None' THEN 1 ELSE 0 END) as nones,
        COUNT(DISTINCT symbol) as symbols_with_signals
      FROM buy_sell_daily
    `);
    
    console.log('\n=== PRICE_DAILY ===');
    console.log(priceResult.rows[0]);
    console.log('\n=== TECHNICAL_DATA_DAILY ===');
    console.log(technicalResult.rows[0]);
    console.log('\n=== BUY_SELL_DAILY SIGNALS ===');
    console.log(signalResult.rows[0]);
    
    process.exit(0);
  } catch (err) {
    console.error('Error:', err.message);
    process.exit(1);
  }
}

checkState();
