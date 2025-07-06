const { Pool } = require('pg');
const { getDbCredentials } = require('../utils/secrets');

let pool;

async function getPool() {
  if (!pool) {
    const creds = await getDbCredentials();
    pool = new Pool({
      host: creds.host,
      port: creds.port || 5432,
      user: creds.username,
      password: creds.password,
      database: creds.dbname,
      max: 20,
      idleTimeoutMillis: 30000,
      connectionTimeoutMillis: 2000,
    });
  }
  return pool;
}

// Get enhanced trading signals with O'Neill methodology
async function getEnhancedSignals(event) {
  const { timeframe = 'daily', signalType = 'all', minStrength = 0, limit = 100 } = event.queryStringParameters || {};
  
  try {
    const pool = await getPool();
    
    let query = `
      WITH latest_signals AS (
        SELECT DISTINCT ON (bs.symbol) 
          bs.*,
          ss.company_name,
          ss.sector,
          ss.exchange,
          ss.market_cap,
          -- Calculate if currently in buy zone
          CASE 
            WHEN bs.buy_zone_start IS NOT NULL AND bs.buy_zone_end IS NOT NULL 
                 AND bs.close >= bs.buy_zone_start AND bs.close <= bs.buy_zone_end 
            THEN true 
            ELSE false 
          END as in_buy_zone,
          -- Calculate position status if in position
          CASE
            WHEN bs.inposition AND bs.current_gain_pct >= 20 THEN 'TARGET_1_REACHED'
            WHEN bs.inposition AND bs.current_gain_pct >= 25 THEN 'TARGET_2_REACHED'
            WHEN bs.inposition AND bs.current_gain_pct <= -7 THEN 'STOP_LOSS_WARNING'
            WHEN bs.inposition THEN 'ACTIVE'
            ELSE 'NO_POSITION'
          END as position_status,
          -- Additional metrics
          cp.trailing_pe,
          cp.forward_pe,
          cp.peg_ratio,
          cp.price_to_book,
          cp.beta
        FROM buy_sell_${timeframe} bs
        JOIN stock_symbols ss ON bs.symbol = ss.symbol
        LEFT JOIN company_profile cp ON bs.symbol = cp.ticker
        WHERE bs.strength >= $1
          ${signalType !== 'all' ? "AND bs.signal = $2" : ''}
        ORDER BY bs.symbol, bs.date DESC
      )
      SELECT * FROM latest_signals
      WHERE signal != 'None'
      ORDER BY 
        CASE 
          WHEN signal = 'Buy' AND in_buy_zone THEN 0
          WHEN signal = 'Buy' THEN 1
          WHEN signal = 'Sell' THEN 2
          ELSE 3
        END,
        strength DESC,
        volume_surge_pct DESC
      LIMIT $${signalType !== 'all' ? '3' : '2'}
    `;
    
    const params = signalType !== 'all' 
      ? [minStrength, signalType, limit]
      : [minStrength, limit];
    
    const result = await pool.query(query, params);
    
    // Process and enhance the signals
    const signals = result.rows.map(row => ({
      // Basic info
      symbol: row.symbol,
      company_name: row.company_name,
      sector: row.sector,
      date: row.date,
      
      // Signal info
      signal: row.signal,
      signal_type: row.signal_type || 'Standard',
      signal_strength: row.strength,
      
      // Price data
      current_price: parseFloat(row.close),
      entry_price: parseFloat(row.entry_price || row.buylevel),
      
      // O'Neill specific fields
      pivot_price: parseFloat(row.pivot_price),
      buy_zone_start: parseFloat(row.buy_zone_start),
      buy_zone_end: parseFloat(row.buy_zone_end),
      in_buy_zone: row.in_buy_zone,
      
      // Exit triggers
      exit_trigger_1_price: parseFloat(row.exit_trigger_1_price),
      exit_trigger_2_price: parseFloat(row.exit_trigger_2_price),
      exit_trigger_3_condition: row.exit_trigger_3_condition,
      exit_trigger_3_price: parseFloat(row.exit_trigger_3_price),
      exit_trigger_4_condition: row.exit_trigger_4_condition,
      exit_trigger_4_price: parseFloat(row.exit_trigger_4_price),
      
      // Stop loss
      initial_stop: parseFloat(row.initial_stop),
      trailing_stop: parseFloat(row.trailing_stop),
      stop_loss: parseFloat(row.stoplevel),
      
      // Base pattern info
      base_type: row.base_type,
      base_length_days: row.base_length_days,
      
      // Volume analysis
      volume: row.volume,
      avg_volume_50d: row.avg_volume_50d,
      volume_surge_pct: parseFloat(row.volume_surge_pct),
      
      // Relative strength
      rs_rating: row.rs_rating,
      breakout_quality: row.breakout_quality,
      
      // Risk/Reward
      risk_reward_ratio: parseFloat(row.risk_reward_ratio),
      
      // Position tracking
      in_position: row.inposition,
      position_status: row.position_status,
      current_gain_pct: parseFloat(row.current_gain_pct),
      days_in_position: row.days_in_position,
      
      // Fundamentals
      market_cap: parseFloat(row.market_cap),
      trailing_pe: parseFloat(row.trailing_pe),
      forward_pe: parseFloat(row.forward_pe),
      peg_ratio: parseFloat(row.peg_ratio),
      price_to_book: parseFloat(row.price_to_book),
      beta: parseFloat(row.beta)
    }));
    
    return {
      statusCode: 200,
      body: JSON.stringify({
        success: true,
        signals: signals,
        count: signals.length,
        timeframe: timeframe,
        filters: {
          signalType,
          minStrength,
          limit
        }
      })
    };
    
  } catch (error) {
    console.error('Error fetching enhanced signals:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({
        success: false,
        error: 'Failed to fetch enhanced trading signals',
        message: error.message
      })
    };
  }
}

// Get active positions with exit zone tracking
async function getActivePositions(event) {
  try {
    const pool = await getPool();
    
    const query = `
      SELECT 
        bs.symbol,
        ss.company_name,
        bs.date as signal_date,
        bs.buylevel as entry_price,
        bs.close as current_price,
        bs.exit_trigger_1_price,
        bs.exit_trigger_2_price,
        bs.exit_trigger_3_condition,
        bs.exit_trigger_3_price,
        bs.exit_trigger_4_condition,
        bs.exit_trigger_4_price,
        bs.initial_stop,
        bs.trailing_stop,
        bs.current_gain_pct,
        bs.days_in_position,
        bs.volume_surge_pct,
        bs.rs_rating,
        bs.breakout_quality,
        -- Calculate which exit zones have been reached
        CASE
          WHEN bs.current_gain_pct >= 25 THEN 'ZONE_2_REACHED'
          WHEN bs.current_gain_pct >= 20 THEN 'ZONE_1_REACHED'
          WHEN bs.close < bs.initial_stop THEN 'STOP_LOSS_WARNING'
          ELSE 'ACTIVE'
        END as position_status,
        -- Calculate shares based on $10k position size
        FLOOR(10000 / bs.buylevel) as shares,
        FLOOR(10000 / bs.buylevel) * bs.close as current_value
      FROM buy_sell_daily bs
      JOIN stock_symbols ss ON bs.symbol = ss.symbol
      WHERE bs.inposition = true
        AND bs.date = (
          SELECT MAX(date) 
          FROM buy_sell_daily 
          WHERE symbol = bs.symbol
        )
      ORDER BY bs.current_gain_pct DESC
    `;
    
    const result = await pool.query(query);
    
    // Group positions by status
    const positions = result.rows;
    const summary = {
      total_positions: positions.length,
      winning_positions: positions.filter(p => p.current_gain_pct > 0).length,
      losing_positions: positions.filter(p => p.current_gain_pct < 0).length,
      zone_1_reached: positions.filter(p => p.current_gain_pct >= 20).length,
      zone_2_reached: positions.filter(p => p.current_gain_pct >= 25).length,
      stop_loss_warnings: positions.filter(p => p.current_gain_pct <= -5).length
    };
    
    return {
      statusCode: 200,
      body: JSON.stringify({
        success: true,
        positions: positions,
        summary: summary
      })
    };
    
  } catch (error) {
    console.error('Error fetching active positions:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({
        success: false,
        error: 'Failed to fetch active positions',
        message: error.message
      })
    };
  }
}

// Get market timing indicators
async function getMarketTiming(event) {
  try {
    const pool = await getPool();
    
    // For now, return mock data - would calculate from actual market data
    const marketTiming = {
      market_status: 'Confirmed Uptrend',
      distribution_days: 2,
      follow_through_day: '2024-01-15',
      sp500_above_50ma: 68,
      sp500_above_200ma: 75,
      nasdaq_above_50ma: 62,
      nasdaq_above_200ma: 71,
      growth_leaders_up: 42,
      growth_leaders_down: 8,
      put_call_ratio: 0.85,
      vix_level: 15.2,
      advance_decline: 1.8,
      new_highs: 145,
      new_lows: 32,
      last_updated: new Date().toISOString()
    };
    
    return {
      statusCode: 200,
      body: JSON.stringify({
        success: true,
        data: marketTiming
      })
    };
    
  } catch (error) {
    console.error('Error fetching market timing:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({
        success: false,
        error: 'Failed to fetch market timing data',
        message: error.message
      })
    };
  }
}

module.exports = {
  getEnhancedSignals,
  getActivePositions,
  getMarketTiming
};