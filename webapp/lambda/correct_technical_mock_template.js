// Complete technical_data_daily mock template with ALL fields from loadtechnicalsdaily.py
const correctTechnicalDataMock = {
  rows: [
    {
      symbol: "AAPL",
      date: "2025-07-16T00:00:00.000Z",
      // Technical indicators
      rsi: 65.8,
      macd: 0.25,
      macd_signal: 0.18,
      macd_hist: 0.07,
      mom: 1.8,
      roc: 3.2,
      adx: 28.4,
      plus_di: 25.2,
      minus_di: 18.6,
      atr: 2.85,
      ad: 1250000.0,
      cmf: 0.15,
      mfi: 58.9,
      // TD Sequential and other indicators
      td_sequential: 5,
      td_combo: 3,
      marketwatch: 0.75,
      dm: 0.45,
      // Moving averages
      sma_10: 174.8,
      sma_20: 172.5,
      sma_50: 168.3,
      sma_150: 165.2,
      sma_200: 163.8,
      // Exponential moving averages
      ema_4: 175.1,
      ema_9: 174.2,
      ema_21: 171.15,
      // Bollinger bands
      bbands_lower: 166.8,
      bbands_middle: 172.65,
      bbands_upper: 178.5,
      // Pivot points
      pivot_high: null,
      pivot_low: 170.5,
      pivot_high_triggered: null,
      pivot_low_triggered: 170.5,
      // Timestamp
      fetched_at: "2025-07-16T10:30:00.000Z"
    }
  ]
};

// Use this template for all technical test mocks
module.exports = correctTechnicalDataMock;