const { query } = require("./database");

/**
 * AI Market Scanner Utility
 * Advanced algorithms for identifying market opportunities
 */

class AIMarketScanner {
  constructor() {
    this.strategies = this.initializeStrategies();
  }

  initializeStrategies() {
    return {
      momentum: {
        name: 'Momentum Breakouts',
        description: 'Stocks with strong price and volume momentum',
        algorithm: this.momentumAlgorithm.bind(this),
        weight: 0.8
      },
      reversal: {
        name: 'Reversal Opportunities', 
        description: 'Oversold stocks showing signs of reversal',
        algorithm: this.reversalAlgorithm.bind(this),
        weight: 0.7
      },
      breakout: {
        name: 'Technical Breakouts',
        description: 'Stocks breaking through resistance levels',
        algorithm: this.breakoutAlgorithm.bind(this),
        weight: 0.85
      },
      unusual: {
        name: 'Unusual Activity',
        description: 'Stocks with unusual volume or price activity',
        algorithm: this.unusualActivityAlgorithm.bind(this),
        weight: 0.9
      },
      earnings: {
        name: 'Earnings Momentum',
        description: 'Stocks with strong earnings-related momentum',
        algorithm: this.earningsAlgorithm.bind(this),
        weight: 0.75
      },
      news_sentiment: {
        name: 'News Sentiment',
        description: 'Stocks with positive news sentiment',
        algorithm: this.newsSentimentAlgorithm.bind(this),
        weight: 0.6
      }
    };
  }

  async scan(type = 'momentum', limit = 50, filters = {}) {
    const strategy = this.strategies[type];
    if (!strategy) {
      throw new Error(`Unknown scan type: ${type}`);
    }

    console.log(`🔍 Running AI scan: ${strategy.name}`);
    
    try {
      const results = await strategy.algorithm(limit, filters);
      
      return {
        scanType: type,
        strategy: strategy.name,
        description: strategy.description,
        results: results,
        totalResults: results.length,
        timestamp: new Date().toISOString(),
        aiWeight: strategy.weight,
        metadata: {
          aiPowered: true,
          realTimeData: true,
          algorithm: type
        }
      };
    } catch (error) {
      console.error(`AI scan failed for ${type}:`, error);
      throw error;
    }
  }

  async momentumAlgorithm(limit, filters) {
    const baseQuery = `
      SELECT DISTINCT
        s.symbol,
        COALESCE(cp.name, s.name) as company_name,
        pd.close as price,
        pd.volume,
        pd_prev.close as prev_price,
        pd_prev.volume as prev_volume,
        ((pd.close - pd_prev.close) / NULLIF(pd_prev.close, 0) * 100) as price_change,
        (pd.volume / NULLIF(pd_prev.volume, 1)) as volume_ratio,
        cp.market_cap,
        cp.sector,
        td.rsi,
        td.sma_20,
        td.sma_50,
        CASE 
          WHEN pd.close > pd_prev.close * 1.05 AND pd.volume > pd_prev.volume * 2.5 THEN 95
          WHEN pd.close > pd_prev.close * 1.03 AND pd.volume > pd_prev.volume * 2.0 THEN 85
          WHEN pd.close > pd_prev.close * 1.02 AND pd.volume > pd_prev.volume * 1.5 THEN 75
          WHEN pd.close > pd_prev.close * 1.01 AND pd.volume > pd_prev.volume * 1.2 THEN 65
          ELSE 50
        END as ai_score
      FROM stocks s
      LEFT JOIN company_profile cp ON s.symbol = cp.ticker
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) *
        FROM price_daily 
        WHERE date = (SELECT MAX(date) FROM price_daily WHERE symbol = price_daily.symbol)
        ORDER BY symbol, date DESC
      ) pd ON s.symbol = pd.symbol
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) *
        FROM price_daily 
        WHERE date = (
          SELECT MAX(date) 
          FROM price_daily 
          WHERE symbol = price_daily.symbol 
          AND date < (SELECT MAX(date) FROM price_daily WHERE symbol = price_daily.symbol)
        )
        ORDER BY symbol, date DESC
      ) pd_prev ON s.symbol = pd_prev.symbol
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) *
        FROM technical_data_daily
        WHERE date = (SELECT MAX(date) FROM technical_data_daily WHERE symbol = technical_data_daily.symbol)
        ORDER BY symbol, date DESC
      ) td ON s.symbol = td.symbol
      WHERE pd.close IS NOT NULL 
        AND pd_prev.close IS NOT NULL
        AND pd.close > pd_prev.close * 1.01
        AND pd.volume > pd_prev.volume * 1.2
        AND pd.close > 5
        AND (cp.market_cap IS NULL OR cp.market_cap > 100000000)
      ORDER BY 
        ((pd.close - pd_prev.close) / NULLIF(pd_prev.close, 0) * 100) * 
        (pd.volume / NULLIF(pd_prev.volume, 1)) DESC
      LIMIT $1
    `;

    const results = await query(baseQuery, [limit]);
    
    return results.rows.map(row => ({
      symbol: row.symbol,
      company_name: row.company_name,
      price: parseFloat(row.price).toFixed(2),
      price_change: parseFloat(row.price_change || 0).toFixed(2),
      volume: parseInt(row.volume || 0),
      volume_ratio: parseFloat(row.volume_ratio || 1).toFixed(2),
      market_cap: row.market_cap,
      sector: row.sector,
      ai_score: parseInt(row.ai_score),
      confidence: this.getConfidenceLevel(row.ai_score),
      signals: this.getMomentumSignals(row),
      technical_indicators: {
        rsi: row.rsi ? parseFloat(row.rsi).toFixed(2) : null,
        above_sma20: row.sma_20 && row.price ? row.price > row.sma_20 : null,
        above_sma50: row.sma_50 && row.price ? row.price > row.sma_50 : null
      },
      scan_timestamp: new Date().toISOString()
    }));
  }

  async reversalAlgorithm(limit, filters) {
    const baseQuery = `
      SELECT DISTINCT
        s.symbol,
        COALESCE(cp.name, s.name) as company_name,
        pd.close as price,
        pd.volume,
        pd_prev.close as prev_price,
        pd_prev.volume as prev_volume,
        ((pd.close - pd_prev.close) / NULLIF(pd_prev.close, 0) * 100) as price_change,
        (pd.volume / NULLIF(pd_prev.volume, 1)) as volume_ratio,
        cp.market_cap,
        cp.sector,
        td.rsi,
        td.sma_20,
        td.sma_50,
        CASE 
          WHEN pd.close < pd_prev.close * 0.85 AND pd.volume > pd_prev.volume * 3.0 AND (td.rsi < 30 OR td.rsi IS NULL) THEN 90
          WHEN pd.close < pd_prev.close * 0.90 AND pd.volume > pd_prev.volume * 2.0 AND (td.rsi < 35 OR td.rsi IS NULL) THEN 80
          WHEN pd.close < pd_prev.close * 0.95 AND pd.volume > pd_prev.volume * 1.5 THEN 70
          WHEN pd.close < pd_prev.close * 0.98 AND pd.volume > pd_prev.volume * 1.3 THEN 60
          ELSE 50
        END as ai_score
      FROM stocks s
      LEFT JOIN company_profile cp ON s.symbol = cp.ticker
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) *
        FROM price_daily 
        WHERE date = (SELECT MAX(date) FROM price_daily WHERE symbol = price_daily.symbol)
        ORDER BY symbol, date DESC
      ) pd ON s.symbol = pd.symbol
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) *
        FROM price_daily 
        WHERE date = (
          SELECT MAX(date) 
          FROM price_daily 
          WHERE symbol = price_daily.symbol 
          AND date < (SELECT MAX(date) FROM price_daily WHERE symbol = price_daily.symbol)
        )
        ORDER BY symbol, date DESC
      ) pd_prev ON s.symbol = pd_prev.symbol
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) *
        FROM technical_data_daily
        WHERE date = (SELECT MAX(date) FROM technical_data_daily WHERE symbol = technical_data_daily.symbol)
        ORDER BY symbol, date DESC
      ) td ON s.symbol = td.symbol
      WHERE pd.close IS NOT NULL 
        AND pd_prev.close IS NOT NULL
        AND pd.close < pd_prev.close * 0.98
        AND pd.volume > pd_prev.volume * 1.3
        AND pd.close > 2
        AND (cp.market_cap IS NULL OR cp.market_cap > 50000000)
      ORDER BY 
        (pd.volume / NULLIF(pd_prev.volume, 1)) * 
        ABS((pd.close - pd_prev.close) / NULLIF(pd_prev.close, 0)) DESC
      LIMIT $1
    `;

    const results = await query(baseQuery, [limit]);
    
    return results.rows.map(row => ({
      symbol: row.symbol,
      company_name: row.company_name,
      price: parseFloat(row.price).toFixed(2),
      price_change: parseFloat(row.price_change || 0).toFixed(2),
      volume: parseInt(row.volume || 0),
      volume_ratio: parseFloat(row.volume_ratio || 1).toFixed(2),
      market_cap: row.market_cap,
      sector: row.sector,
      ai_score: parseInt(row.ai_score),
      confidence: this.getConfidenceLevel(row.ai_score),
      signals: this.getReversalSignals(row),
      technical_indicators: {
        rsi: row.rsi ? parseFloat(row.rsi).toFixed(2) : null,
        oversold: row.rsi ? row.rsi < 30 : null,
        below_sma20: row.sma_20 && row.price ? row.price < row.sma_20 : null,
        below_sma50: row.sma_50 && row.price ? row.price < row.sma_50 : null
      },
      scan_timestamp: new Date().toISOString()
    }));
  }

  async breakoutAlgorithm(limit, filters) {
    const baseQuery = `
      SELECT DISTINCT
        s.symbol,
        COALESCE(cp.name, s.name) as company_name,
        pd.close as price,
        pd.high,
        pd.low,
        pd.volume,
        pd_prev.close as prev_price,
        pd_prev.volume as prev_volume,
        ((pd.close - pd_prev.close) / NULLIF(pd_prev.close, 0) * 100) as price_change,
        (pd.volume / NULLIF(pd_prev.volume, 1)) as volume_ratio,
        cp.market_cap,
        cp.sector,
        td.sma_20,
        td.sma_50,
        CASE 
          WHEN pd.close >= pd.high * 0.99 AND pd.close > pd.open * 1.03 AND pd.volume > pd_prev.volume * 2.0 THEN 92
          WHEN pd.close >= pd.high * 0.98 AND pd.close > pd.open * 1.02 AND pd.volume > pd_prev.volume * 1.5 THEN 82
          WHEN pd.close > pd.open * 1.02 AND pd.volume > pd_prev.volume * 1.3 THEN 72
          ELSE 60
        END as ai_score
      FROM stocks s
      LEFT JOIN company_profile cp ON s.symbol = cp.ticker
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) *
        FROM price_daily 
        WHERE date = (SELECT MAX(date) FROM price_daily WHERE symbol = price_daily.symbol)
        ORDER BY symbol, date DESC
      ) pd ON s.symbol = pd.symbol
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) *
        FROM price_daily 
        WHERE date = (
          SELECT MAX(date) 
          FROM price_daily 
          WHERE symbol = price_daily.symbol 
          AND date < (SELECT MAX(date) FROM price_daily WHERE symbol = price_daily.symbol)
        )
        ORDER BY symbol, date DESC
      ) pd_prev ON s.symbol = pd_prev.symbol
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) *
        FROM technical_data_daily
        WHERE date = (SELECT MAX(date) FROM technical_data_daily WHERE symbol = technical_data_daily.symbol)
        ORDER BY symbol, date DESC
      ) td ON s.symbol = td.symbol
      WHERE pd.close IS NOT NULL 
        AND pd_prev.close IS NOT NULL
        AND pd.close >= pd.high * 0.97
        AND pd.close > pd.open * 1.01
        AND pd.volume > pd_prev.volume * 1.2
        AND pd.close > 5
        AND (cp.market_cap IS NULL OR cp.market_cap > 100000000)
      ORDER BY 
        (pd.close / NULLIF(pd.high, 0)) * 
        (pd.volume / NULLIF(pd_prev.volume, 1)) DESC
      LIMIT $1
    `;

    const results = await query(baseQuery, [limit]);
    
    return results.rows.map(row => ({
      symbol: row.symbol,
      company_name: row.company_name,
      price: parseFloat(row.price).toFixed(2),
      high: parseFloat(row.high || 0).toFixed(2),
      low: parseFloat(row.low || 0).toFixed(2),
      price_change: parseFloat(row.price_change || 0).toFixed(2),
      volume: parseInt(row.volume || 0),
      volume_ratio: parseFloat(row.volume_ratio || 1).toFixed(2),
      market_cap: row.market_cap,
      sector: row.sector,
      ai_score: parseInt(row.ai_score),
      confidence: this.getConfidenceLevel(row.ai_score),
      signals: this.getBreakoutSignals(row),
      technical_indicators: {
        near_high: row.high && row.price ? (row.price / row.high >= 0.98) : null,
        above_sma20: row.sma_20 && row.price ? row.price > row.sma_20 : null,
        above_sma50: row.sma_50 && row.price ? row.price > row.sma_50 : null
      },
      scan_timestamp: new Date().toISOString()
    }));
  }

  async unusualActivityAlgorithm(limit, filters) {
    const baseQuery = `
      SELECT DISTINCT
        s.symbol,
        COALESCE(cp.name, s.name) as company_name,
        pd.close as price,
        pd.volume,
        pd_prev.volume as prev_volume,
        pd_avg.avg_volume,
        ((pd.close - pd_prev.close) / NULLIF(pd_prev.close, 0) * 100) as price_change,
        (pd.volume / NULLIF(pd_prev.volume, 1)) as volume_ratio,
        (pd.volume / NULLIF(pd_avg.avg_volume, 1)) as volume_vs_avg,
        cp.market_cap,
        cp.sector,
        CASE 
          WHEN pd.volume > pd_avg.avg_volume * 10 THEN 95
          WHEN pd.volume > pd_avg.avg_volume * 5 THEN 88
          WHEN pd.volume > pd_prev.volume * 5 THEN 85
          WHEN pd.volume > pd_avg.avg_volume * 3 THEN 78
          WHEN pd.volume > pd_prev.volume * 3 THEN 75
          WHEN pd.volume > pd_avg.avg_volume * 2 THEN 68
          ELSE 50
        END as ai_score
      FROM stocks s
      LEFT JOIN company_profile cp ON s.symbol = cp.ticker
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) *
        FROM price_daily 
        WHERE date = (SELECT MAX(date) FROM price_daily WHERE symbol = price_daily.symbol)
        ORDER BY symbol, date DESC
      ) pd ON s.symbol = pd.symbol
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) *
        FROM price_daily 
        WHERE date = (
          SELECT MAX(date) 
          FROM price_daily 
          WHERE symbol = price_daily.symbol 
          AND date < (SELECT MAX(date) FROM price_daily WHERE symbol = price_daily.symbol)
        )
        ORDER BY symbol, date DESC
      ) pd_prev ON s.symbol = pd_prev.symbol
      LEFT JOIN (
        SELECT 
          symbol,
          AVG(volume) as avg_volume
        FROM price_daily
        WHERE date >= (SELECT MAX(date) FROM price_daily) - INTERVAL '30 days'
        GROUP BY symbol
      ) pd_avg ON s.symbol = pd_avg.symbol
      WHERE pd.volume IS NOT NULL
        AND (pd_prev.volume IS NOT NULL OR pd_avg.avg_volume IS NOT NULL)
        AND (
          pd.volume > COALESCE(pd_prev.volume * 2.5, 0) OR 
          pd.volume > COALESCE(pd_avg.avg_volume * 2, 0)
        )
        AND pd.close > 1
        AND (cp.market_cap IS NULL OR cp.market_cap > 10000000)
      ORDER BY 
        GREATEST(
          pd.volume / NULLIF(pd_prev.volume, 1),
          pd.volume / NULLIF(pd_avg.avg_volume, 1)
        ) DESC
      LIMIT $1
    `;

    const results = await query(baseQuery, [limit]);
    
    return results.rows.map(row => ({
      symbol: row.symbol,
      company_name: row.company_name,
      price: parseFloat(row.price).toFixed(2),
      price_change: parseFloat(row.price_change || 0).toFixed(2),
      volume: parseInt(row.volume || 0),
      prev_volume: parseInt(row.prev_volume || 0),
      avg_volume: parseInt(row.avg_volume || 0),
      volume_ratio: parseFloat(row.volume_ratio || 1).toFixed(2),
      volume_vs_avg: parseFloat(row.volume_vs_avg || 1).toFixed(2),
      market_cap: row.market_cap,
      sector: row.sector,
      ai_score: parseInt(row.ai_score),
      confidence: this.getConfidenceLevel(row.ai_score),
      signals: this.getUnusualActivitySignals(row),
      scan_timestamp: new Date().toISOString()
    }));
  }

  async earningsAlgorithm(limit, filters) {
    const baseQuery = `
      SELECT DISTINCT
        s.symbol,
        COALESCE(cp.name, s.name) as company_name,
        pd.close as price,
        pd.volume,
        ((pd.close - pd_prev.close) / NULLIF(pd_prev.close, 0) * 100) as price_change,
        er.report_date,
        er.estimated_eps,
        er.actual_eps,
        er.eps_surprise,
        er.surprise_percent,
        cp.market_cap,
        cp.sector,
        CASE 
          WHEN er.surprise_percent > 20 AND ABS(EXTRACT(DAYS FROM (CURRENT_DATE - er.report_date))) <= 2 THEN 90
          WHEN er.surprise_percent > 10 AND ABS(EXTRACT(DAYS FROM (CURRENT_DATE - er.report_date))) <= 3 THEN 80
          WHEN er.surprise_percent > 5 AND ABS(EXTRACT(DAYS FROM (CURRENT_DATE - er.report_date))) <= 5 THEN 70
          WHEN er.report_date >= CURRENT_DATE - INTERVAL '2 days' THEN 65
          ELSE 55
        END as ai_score
      FROM stocks s
      LEFT JOIN company_profile cp ON s.symbol = cp.ticker
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) *
        FROM price_daily 
        WHERE date = (SELECT MAX(date) FROM price_daily WHERE symbol = price_daily.symbol)
        ORDER BY symbol, date DESC
      ) pd ON s.symbol = pd.symbol
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) *
        FROM price_daily 
        WHERE date = (
          SELECT MAX(date) 
          FROM price_daily 
          WHERE symbol = price_daily.symbol 
          AND date < (SELECT MAX(date) FROM price_daily WHERE symbol = price_daily.symbol)
        )
        ORDER BY symbol, date DESC
      ) pd_prev ON s.symbol = pd_prev.symbol
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) *
        FROM earnings_reports
        WHERE report_date >= CURRENT_DATE - INTERVAL '7 days'
        ORDER BY symbol, report_date DESC
      ) er ON s.symbol = er.symbol
      WHERE er.report_date IS NOT NULL
        AND pd.close IS NOT NULL
        AND (er.surprise_percent > 0 OR er.report_date >= CURRENT_DATE - INTERVAL '2 days')
        AND (cp.market_cap IS NULL OR cp.market_cap > 100000000)
      ORDER BY 
        COALESCE(er.surprise_percent, 0) DESC,
        ABS(EXTRACT(DAYS FROM (CURRENT_DATE - er.report_date))) ASC
      LIMIT $1
    `;

    try {
      const results = await query(baseQuery, [limit]);
      
      return results.rows.map(row => ({
        symbol: row.symbol,
        company_name: row.company_name,
        price: parseFloat(row.price).toFixed(2),
        price_change: parseFloat(row.price_change || 0).toFixed(2),
        market_cap: row.market_cap,
        sector: row.sector,
        earnings: {
          report_date: row.report_date,
          estimated_eps: row.estimated_eps,
          actual_eps: row.actual_eps,
          surprise_percent: row.surprise_percent
        },
        ai_score: parseInt(row.ai_score),
        confidence: this.getConfidenceLevel(row.ai_score),
        signals: this.getEarningsSignals(row),
        scan_timestamp: new Date().toISOString()
      }));
    } catch (error) {
      console.log("Earnings table not available, returning empty results");
      return [];
    }
  }

  async newsSentimentAlgorithm(limit, filters) {
    const baseQuery = `
      SELECT DISTINCT
        s.symbol,
        COALESCE(cp.name, s.name) as company_name,
        pd.close as price,
        ((pd.close - pd_prev.close) / NULLIF(pd_prev.close, 0) * 100) as price_change,
        n.sentiment,
        n.sentiment_confidence,
        n.headline,
        n.published_at,
        cp.market_cap,
        cp.sector,
        CASE 
          WHEN n.sentiment > 0.8 AND n.sentiment_confidence > 0.7 THEN 85
          WHEN n.sentiment > 0.6 AND n.sentiment_confidence > 0.6 THEN 75
          WHEN n.sentiment > 0.4 AND n.sentiment_confidence > 0.5 THEN 65
          ELSE 55
        END as ai_score
      FROM stocks s
      LEFT JOIN company_profile cp ON s.symbol = cp.ticker
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) *
        FROM price_daily 
        WHERE date = (SELECT MAX(date) FROM price_daily WHERE symbol = price_daily.symbol)
        ORDER BY symbol, date DESC
      ) pd ON s.symbol = pd.symbol
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) *
        FROM price_daily 
        WHERE date = (
          SELECT MAX(date) 
          FROM price_daily 
          WHERE symbol = price_daily.symbol 
          AND date < (SELECT MAX(date) FROM price_daily WHERE symbol = price_daily.symbol)
        )
        ORDER BY symbol, date DESC
      ) pd_prev ON s.symbol = pd_prev.symbol
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) 
          symbol, sentiment, sentiment_confidence, headline, published_at
        FROM news
        WHERE published_at >= CURRENT_DATE - INTERVAL '2 days'
        ORDER BY symbol, published_at DESC
      ) n ON s.symbol = n.symbol
      WHERE n.sentiment IS NOT NULL
        AND n.sentiment > 0.3
        AND pd.close IS NOT NULL
        AND (cp.market_cap IS NULL OR cp.market_cap > 50000000)
      ORDER BY 
        (n.sentiment * n.sentiment_confidence) DESC
      LIMIT $1
    `;

    try {
      const results = await query(baseQuery, [limit]);
      
      return results.rows.map(row => ({
        symbol: row.symbol,
        company_name: row.company_name,
        price: parseFloat(row.price).toFixed(2),
        price_change: parseFloat(row.price_change || 0).toFixed(2),
        market_cap: row.market_cap,
        sector: row.sector,
        news: {
          sentiment: parseFloat(row.sentiment).toFixed(3),
          confidence: parseFloat(row.sentiment_confidence).toFixed(3),
          headline: row.headline,
          published_at: row.published_at
        },
        ai_score: parseInt(row.ai_score),
        confidence: this.getConfidenceLevel(row.ai_score),
        signals: this.getNewsSentimentSignals(row),
        scan_timestamp: new Date().toISOString()
      }));
    } catch (error) {
      console.log("News table not available, returning empty results");
      return [];
    }
  }

  getConfidenceLevel(score) {
    if (score >= 85) return 'very high';
    if (score >= 75) return 'high';
    if (score >= 65) return 'medium';
    if (score >= 55) return 'low';
    return 'very low';
  }

  getMomentumSignals(row) {
    const signals = [];
    if (row.price_change > 5) signals.push('Strong Price Gain');
    if (row.volume_ratio > 2) signals.push('High Volume');
    if (row.price_change > 2 && row.volume_ratio > 1.5) signals.push('Price-Volume Momentum');
    if (row.rsi > 70) signals.push('Overbought RSI');
    return signals.length > 0 ? signals : ['Momentum Signal'];
  }

  getReversalSignals(row) {
    const signals = [];
    if (row.price_change < -5) signals.push('Oversold Condition');
    if (row.volume_ratio > 2) signals.push('Volume Spike');
    if (row.rsi < 30) signals.push('RSI Oversold');
    if (Math.abs(row.price_change) > 3 && row.volume_ratio > 1.5) signals.push('Reversal Setup');
    return signals.length > 0 ? signals : ['Reversal Signal'];
  }

  getBreakoutSignals(row) {
    const signals = [];
    if (row.price >= row.high * 0.99) signals.push('New High');
    if (row.volume_ratio > 1.5) signals.push('Volume Breakout');
    if (row.price_change > 2) signals.push('Price Breakout');
    if (row.above_sma20 && row.above_sma50) signals.push('Above Moving Averages');
    return signals.length > 0 ? signals : ['Breakout Signal'];
  }

  getUnusualActivitySignals(row) {
    const signals = [];
    if (row.volume_ratio > 5) signals.push('Extreme Volume');
    if (row.volume_vs_avg > 3) signals.push('Above Average Volume');
    if (row.volume_ratio > 2) signals.push('Unusual Volume');
    if (Math.abs(row.price_change) > 5) signals.push('Price Movement');
    return signals.length > 0 ? signals : ['Unusual Activity'];
  }

  getEarningsSignals(row) {
    const signals = [];
    if (row.surprise_percent > 20) signals.push('Big Earnings Beat');
    if (row.surprise_percent > 10) signals.push('Earnings Beat');
    if (row.surprise_percent > 0) signals.push('Positive Surprise');
    if (row.report_date) signals.push('Recent Earnings');
    return signals.length > 0 ? signals : ['Earnings Signal'];
  }

  getNewsSentimentSignals(row) {
    const signals = [];
    if (row.sentiment > 0.8) signals.push('Very Positive News');
    if (row.sentiment > 0.6) signals.push('Positive News');
    if (row.sentiment_confidence > 0.7) signals.push('High Confidence');
    if (row.headline) signals.push('Recent News');
    return signals.length > 0 ? signals : ['News Sentiment'];
  }

  getAvailableStrategies() {
    return Object.keys(this.strategies).map(key => ({
      type: key,
      name: this.strategies[key].name,
      description: this.strategies[key].description,
      weight: this.strategies[key].weight
    }));
  }
}

module.exports = { AIMarketScanner };