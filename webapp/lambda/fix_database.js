const { query } = require('./utils/database');

async function fixDatabase() {
  try {
    console.log('Fixing database schema issues...');
    
    // Drop and recreate technical_data_daily with correct columns
    await query('DROP TABLE IF EXISTS technical_data_daily CASCADE');
    
    await query(`
      CREATE TABLE technical_data_daily (
        symbol VARCHAR(50),
        date TIMESTAMP,
        rsi DOUBLE PRECISION,
        macd DOUBLE PRECISION,
        macd_signal DOUBLE PRECISION,
        macd_hist DOUBLE PRECISION,
        mom DOUBLE PRECISION,
        roc DOUBLE PRECISION,
        adx DOUBLE PRECISION,
        plus_di DOUBLE PRECISION,
        minus_di DOUBLE PRECISION,
        atr DOUBLE PRECISION,
        ad DOUBLE PRECISION,
        cmf DOUBLE PRECISION,
        mfi DOUBLE PRECISION,
        td_sequential INTEGER,
        td_combo INTEGER,
        marketwatch DOUBLE PRECISION,
        dm DOUBLE PRECISION,
        sma_10 DOUBLE PRECISION,
        sma_20 DOUBLE PRECISION,
        sma_50 DOUBLE PRECISION,
        sma_150 DOUBLE PRECISION,
        sma_200 DOUBLE PRECISION,
        ema_4 DOUBLE PRECISION,
        ema_9 DOUBLE PRECISION,
        ema_21 DOUBLE PRECISION,
        bbands_lower DOUBLE PRECISION,
        bbands_middle DOUBLE PRECISION,
        bbands_upper DOUBLE PRECISION,
        pivot_high DOUBLE PRECISION,
        pivot_low DOUBLE PRECISION,
        pivot_high_triggered BOOLEAN,
        pivot_low_triggered BOOLEAN,
        fetched_at TIMESTAMP
      )
    `);
    
    // Insert test data
    await query(`
      INSERT INTO technical_data_daily (symbol, date, rsi, macd, macd_signal, macd_hist, mom, roc, adx, plus_di, minus_di, atr, ad, cmf, mfi, td_sequential, td_combo, marketwatch, dm, sma_10, sma_20, sma_50, sma_150, sma_200, ema_4, ema_9, ema_21, bbands_lower, bbands_middle, bbands_upper, pivot_high, pivot_low, pivot_high_triggered, pivot_low_triggered, fetched_at) VALUES
      ('AAPL', '2024-01-01', 65.4, 0.82, 0.75, 0.07, 2.1, 3.2, 45.2, 25.1, 18.7, 1.8, 125000, 0.15, 72.3, 9, 13, 0.5, 1.2, 180.25, 178.50, 175.80, 170.25, 165.90, 181.10, 179.85, 177.20, 174.50, 179.25, 184.00, 182.00, 176.50, false, false, '2024-01-01 09:30:00'),
      ('MSFT', '2024-01-01', 58.2, 1.45, 1.32, 0.13, 3.8, 4.5, 52.8, 28.4, 21.2, 2.1, 180000, 0.22, 68.9, 7, 11, 0.6, 1.5, 425.30, 422.80, 418.50, 410.25, 405.90, 426.10, 424.85, 421.20, 420.50, 425.25, 430.00, 428.00, 418.50, false, false, '2024-01-01 09:30:00')
      ON CONFLICT DO NOTHING
    `);
    
    console.log('✅ Database schema fixed successfully');
    process.exit(0);
  } catch (error) {
    console.error('❌ Error fixing database:', error);
    process.exit(1);
  }
}

fixDatabase();
