const { Pool } = require('pg');

const pool = new Pool({
  host: 'localhost',
  port: 5432,
  user: 'postgres',
  password: process.env.DB_PASSWORD || '',
  database: 'stocks',
  ssl: false
});

const sectors = ['Technology', 'Healthcare', 'Financials', 'Industrials', 'Consumer Discretionary', 'Energy', 'Materials', 'Real Estate', 'Utilities', 'Consumer Staples'];
const industries = {
  'Technology': ['Software', 'Semiconductors', 'Hardware'],
  'Healthcare': ['Biotech', 'Pharmaceuticals', 'Medical Devices'],
  'Financials': ['Banks', 'Insurance', 'Investment Management'],
  'Industrials': ['Machinery', 'Aerospace', 'Engineering'],
  'Consumer Discretionary': ['Retail', 'Automotive', 'Restaurants'],
  'Energy': ['Oil & Gas', 'Renewables'],
  'Materials': ['Chemicals', 'Metals'],
  'Real Estate': ['REITs'],
  'Utilities': ['Electric'],
  'Consumer Staples': ['Food', 'Beverages']
};

async function populateTestData() {
  try {
    console.log('Populating complete test data for all 10K stocks...\n');

    const stocksResult = await pool.query('SELECT DISTINCT symbol FROM stock_scores ORDER BY symbol');
    const stocks = stocksResult.rows.map(r => r.symbol);
    console.log(`Found ${stocks.length} stocks\n`);

    // 1. Populate company_profile (sector, industry)
    console.log('1. Populating company_profile with sectors & industries...');
    await pool.query('DELETE FROM company_profile');
    for (let i = 0; i < stocks.length; i += 500) {
      const batch = stocks.slice(i, i + 500);
      const values = batch.map(sym => {
        const sector = sectors[Math.floor(Math.random() * sectors.length)];
        const industryList = industries[sector] || ['Unknown'];
        const industry = industryList[Math.floor(Math.random() * industryList.length)];
        return `('${sym}', '${sector}', '${industry}', NOW())`;
      }).join(',');
      await pool.query(`
        INSERT INTO company_profile (ticker, sector, industry, created_at)
        VALUES ${values}
      `);
      process.stdout.write(`  ${Math.min(i + 500, stocks.length)}/${stocks.length}\r`);
    }
    console.log(`  ✓ ${stocks.length} rows\n`);

    // 2. Populate buy_sell_daily (trading signals - minimal fields)
    console.log('2. Populating buy_sell_daily signals...');
    await pool.query('DELETE FROM buy_sell_daily');
    const today = new Date().toISOString().split('T')[0];
    for (let i = 0; i < stocks.length; i += 500) {
      const batch = stocks.slice(i, i < 500 ? i + 500 : stocks.length);
      const values = batch.map(sym => {
        const signal = Math.random() > 0.6 ? 'buy' : (Math.random() > 0.5 ? 'sell' : 'hold');
        const strength = 50 + Math.random() * 50;
        return `('${sym}', '${today}', '${signal}', ${strength}, NOW())`;
      }).join(',');
      await pool.query(`
        INSERT INTO buy_sell_daily (symbol, date, signal, strength, created_at)
        VALUES ${values}
      `);
      process.stdout.write(`  ${Math.min(i + 500, stocks.length)}/${stocks.length}\r`);
    }
    console.log(`  ✓ ${stocks.length} rows\n`);

    // 3. Populate technical_data_daily (RSI, SMA, etc.)
    console.log('3. Populating technical_data_daily indicators...');
    await pool.query('DELETE FROM technical_data_daily');
    for (let i = 0; i < stocks.length; i += 500) {
      const batch = stocks.slice(i, i < 500 ? i + 500 : stocks.length);
      const values = batch.map(sym => `(
        '${sym}', '${today}',
        ${40 + Math.random() * 20}, ${20 + Math.random() * 10}, ${30 + Math.random() * 10}, ${10 + Math.random() * 5},
        ${5 + Math.random() * 3}, ${50 + Math.random() * 20}, ${0.5 + Math.random() * 0.2},
        ${100 + Math.random() * 20}, ${150 + Math.random() * 50}, ${80 + Math.random() * 40},
        NOW(), ${100 + Math.random() * 50}
      )`).join(',');
      await pool.query(`
        INSERT INTO technical_data_daily (symbol, date, rsi, atr, adx, plus_di, minus_di, sma_50, roc, sma_20, sma_200, ema_12, created_at, close)
        VALUES ${values}
      `);
      process.stdout.write(`  ${Math.min(i + 500, stocks.length)}/${stocks.length}\r`);
    }
    console.log(`  ✓ ${stocks.length} rows\n`);

    // 4. Populate backtest_results
    console.log('4. Populating backtest results...');
    await pool.query('DELETE FROM backtest_results');
    const strategies = ['RSI', 'SMA_Crossover', 'Bollinger_Bands', 'MACD'];
    for (const strategy of strategies) {
      await pool.query(`
        INSERT INTO backtest_results (strategy_name, total_return_pct, max_drawdown_pct, sharpe_ratio, win_rate_pct, total_trades, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, NOW())
      `, [strategy, 15 + Math.random() * 30, 5 + Math.random() * 20, 1 + Math.random() * 2, 45 + Math.random() * 30, 50 + Math.random() * 200]);
    }
    console.log(`  ✓ ${strategies.length} strategies\n`);

    console.log('✅ Complete test data population finished!\n');

  } catch (error) {
    console.error('❌ Error:', error.message);
    console.error(error);
  } finally {
    await pool.end();
  }
}

populateTestData();
