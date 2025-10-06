// Real trading signals endpoint - replaces mock data
const express = require("express");
const { query } = require("../utils/database");

const router = express.Router();

// Get trading signals from buy_sell_daily table
router.get("/signals", async (req, res) => {
  try {
    const { limit = 100, symbol, signal_type, timeframe = "daily" } = req.query;

    console.log(`🎯 Trading signals requested - symbol: ${symbol}, type: ${signal_type}, limit: ${limit}`);

    // Validate limit
    const limitNum = parseInt(limit);
    if (isNaN(limitNum) || limitNum <= 0) {
      return res.status(400).json({
        success: false,
        error: "Limit must be a positive number",
      });
    }
    if (limitNum > 500) {
      return res.status(400).json({
        success: false,
        error: "Limit cannot exceed 500",
      });
    }

    // Build query
    let queryText = `
      SELECT
        symbol,
        date,
        signal,
        close_price,
        sma_20,
        sma_50,
        rsi,
        macd,
        macd_signal,
        bb_upper,
        bb_lower,
        volume
      FROM buy_sell_daily
      WHERE 1=1
    `;

    const queryParams = [];
    let paramIndex = 1;

    // Add filters
    if (symbol) {
      queryText += ` AND symbol = $${paramIndex}`;
      queryParams.push(symbol.toUpperCase());
      paramIndex++;
    }

    if (signal_type) {
      const signalMap = {
        'buy': 1,
        'sell': -1,
        'hold': 0
      };
      const signalValue = signalMap[signal_type.toLowerCase()];
      if (signalValue !== undefined) {
        queryText += ` AND signal = $${paramIndex}`;
        queryParams.push(signalValue);
        paramIndex++;
      }
    }

    queryText += ` ORDER BY date DESC LIMIT $${paramIndex}`;
    queryParams.push(limitNum);

    console.log('📊 Executing query:', queryText.replace(/\s+/g, ' '), queryParams);

    const result = await query(queryText, queryParams);

    if (!result || !result.rows) {
      console.error('❌ Database query returned null');
      return res.status(500).json({
        success: false,
        error: "Database error - no results",
      });
    }

    if (result.rows.length === 0) {
      console.warn('⚠️ No trading signals found for filters:', { symbol, signal_type });
      return res.json({
        success: true,
        data: [],
        count: 0,
        message: "No signals found matching filters",
      });
    }

    // Transform to frontend format
    const signals = result.rows.map(row => {
      const signalTypeMap = { 1: 'buy', '-1': 'sell', 0: 'hold' };
      const signalType = signalTypeMap[row.signal] || 'hold';

      // Calculate confidence from indicators
      let confidence = 0.5;
      if (row.rsi && row.macd) {
        if (signalType === 'buy' && row.rsi < 40 && row.macd > row.macd_signal) {
          confidence = 0.75;
        } else if (signalType === 'sell' && row.rsi > 60 && row.macd < row.macd_signal) {
          confidence = 0.75;
        } else {
          confidence = 0.55;
        }
      }

      const price = parseFloat(row.close_price) || 0;
      const volatility = 0.05;

      return {
        id: `sig_${row.symbol}_${row.date}`,
        symbol: row.symbol,
        signal_type: signalType,
        timeframe: timeframe,
        price: price,
        target_price: signalType === 'buy' ? price * 1.075 : price * 0.925,
        stop_loss: signalType === 'buy' ? price * 0.95 : price * 1.05,
        confidence: confidence,
        strength: confidence > 0.7 ? 'strong' : 'moderate',
        date: row.date,
        generated_at: row.date,
        indicators: {
          rsi: row.rsi ? parseFloat(row.rsi) : null,
          macd: row.macd ? parseFloat(row.macd) : null,
          sma_20: row.sma_20 ? parseFloat(row.sma_20) : null,
          sma_50: row.sma_50 ? parseFloat(row.sma_50) : null,
        },
        volume: row.volume ? parseInt(row.volume) : null,
        risk_level: confidence > 0.7 ? 'low' : 'medium',
      };
    });

    // Analytics
    const analytics = {
      total_signals: signals.length,
      buy_signals: signals.filter(s => s.signal_type === 'buy').length,
      sell_signals: signals.filter(s => s.signal_type === 'sell').length,
      hold_signals: signals.filter(s => s.signal_type === 'hold').length,
      avg_confidence: signals.length > 0
        ? Math.round((signals.reduce((sum, s) => sum + s.confidence, 0) / signals.length) * 100) / 100
        : 0,
    };

    console.log(`✅ Returned ${signals.length} signals from database`);

    res.json({
      success: true,
      data: signals,
      analytics: analytics,
      count: signals.length,
      data_source: 'buy_sell_daily',
      timestamp: new Date().toISOString(),
    });

  } catch (error) {
    console.error("❌ Trading signals error:", error);
    return res.status(500).json({
      success: false,
      error: "Failed to fetch trading signals from database",
      details: error.message,
    });
  }
});

module.exports = router;
