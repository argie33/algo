/**
 * Market Data Utilities
 *
 * Provides dynamic market data including:
 * - Dynamic risk-free rate (10Y Treasury yield)
 * - Market regime indicators (VIX, yield curve, spreads)
 * - Inflation expectations
 *
 * This replaces hardcoded values with real-time market data
 */

const axios = require('axios');
const db = require('./database');

// NO CACHING - Always fetch fresh market data for financial accuracy

const FRED_API_URL = 'https://api.stlouisfed.org/fred/series/data';

/**
 * Fetch 10-Year Treasury Yield (Risk-Free Rate)
 *
 * Uses FRED API (Federal Reserve Economic Data)
 * Fallback: If API unavailable, uses cached or default value
 *
 * @returns {Promise<number>} Risk-free rate as percentage (e.g., 4.2 for 4.2%)
 */
async function getDynamicRiskFreeRate() {
  try {
    const fredApiKey = process.env.FRED_API_KEY;
    if (!fredApiKey) {
      console.warn('⚠️ FRED_API_KEY not configured - using default 4.5%');
      return 4.5; // Default if no API key
    }

    // Fetch 10-Year Treasury yield (DGS10) - ALWAYS FRESH
    const response = await axios.get(FRED_API_URL, {
      params: {
        series_id: 'DGS10',
        api_key: fredApiKey,
        limit: 1,
        sort_order: 'desc'
      },
      timeout: 5000
    });

    if (response.data?.observations?.[0]?.value) {
      const yieldValue = parseFloat(response.data.observations[0].value);

      if (!isNaN(yieldValue)) {
        console.log(`✓ Dynamic risk-free rate: ${yieldValue}% (from FRED)`);
        return yieldValue;
      }
    }

    console.warn('⚠️ Invalid FRED data - using default 4.5%');
    return 4.5;
  } catch (error) {
    console.warn('⚠️ Error fetching risk-free rate from FRED:', error.message);
    console.log('Using default risk-free rate: 4.5%');
    return 4.5;
  }
}

/**
 * Detect Current Market Regime
 *
 * Analyzes VIX, yield curve slope, credit spreads
 * Returns: 'BULL', 'NEUTRAL', or 'BEAR'
 *
 * @returns {Promise<Object>} Market regime with details
 */
async function getMarketRegime() {
  try {
    // Always fetch fresh market regime - no caching
    // Query market data from database
    const result = await db.query(`
      SELECT
        market_data.vix_index as vix,
        market_data.yield_curve_slope as yield_slope,
        market_data.credit_spreads as spreads
      FROM market_data
      ORDER BY date DESC
      LIMIT 1
    `);

    let regime = 'NEUTRAL'; // Default
    let confidence = 50;
    let reasoning = [];

    if (result.rows && result.rows[0]) {
      const data = result.rows[0];

      // VIX-based classification
      if (data.vix !== null) {
        if (data.vix < 15) {
          regime = 'BULL';
          confidence += 15;
          reasoning.push(`VIX ${data.vix} (low volatility)`);
        } else if (data.vix > 25) {
          regime = 'BEAR';
          confidence += 15;
          reasoning.push(`VIX ${data.vix} (high volatility)`);
        }
      }

      // Yield curve-based classification
      if (data.yield_slope !== null) {
        if (data.yield_slope > 1) {
          if (regime !== 'BEAR') regime = 'BULL';
          confidence += 10;
          reasoning.push(`Steep yield curve (+${data.yield_slope.toFixed(2)})`);
        } else if (data.yield_slope < -0.5) {
          regime = 'BEAR';
          confidence += 15;
          reasoning.push(`Inverted yield curve (${data.yield_slope.toFixed(2)})`);
        }
      }

      // Credit spreads-based classification
      if (data.spreads !== null) {
        if (data.spreads < 150) {
          if (regime !== 'BEAR') regime = 'BULL';
          reasoning.push(`Tight spreads (${data.spreads}bp)`);
        } else if (data.spreads > 250) {
          regime = 'BEAR';
          reasoning.push(`Wide spreads (${data.spreads}bp)`);
        }
      }
    }

    const marketRegimeData = {
      regime,
      confidence: Math.min(100, confidence),
      reasoning: reasoning.length > 0 ? reasoning : ['Insufficient market data'],
      constraints: getRegimeConstraints(regime)
    };

    console.log(`✓ Market Regime: ${regime} (confidence ${marketRegimeData.confidence}%)`);
    return marketRegimeData;
  } catch (error) {
    console.warn('⚠️ Error detecting market regime:', error.message);

    return {
      regime: 'NEUTRAL',
      confidence: 50,
      reasoning: ['Unable to determine - using neutral assumptions'],
      constraints: getRegimeConstraints('NEUTRAL')
    };
  }
}

/**
 * Get portfolio constraints based on market regime
 *
 * @param {string} regime - 'BULL', 'NEUTRAL', or 'BEAR'
 * @returns {Object} Adjusted constraint limits
 */
function getRegimeConstraints(regime) {
  const constraints = {
    'BULL': {
      maxPositionSize: 0.35,      // Can take larger positions
      maxSectorWeight: 0.45,
      riskTolerance: 'HIGH',
      description: 'Bull market - can take more concentrated positions'
    },
    'NEUTRAL': {
      maxPositionSize: 0.25,      // Standard constraints
      maxSectorWeight: 0.35,
      riskTolerance: 'MEDIUM',
      description: 'Neutral environment - balanced approach'
    },
    'BEAR': {
      maxPositionSize: 0.15,      // More defensive, diversified
      maxSectorWeight: 0.25,
      riskTolerance: 'LOW',
      description: 'Bear market - increase diversification, reduce concentration'
    }
  };

  return constraints[regime] || constraints['NEUTRAL'];
}

/**
 * Get inflation expectations
 *
 * Uses Fed PCE inflation expectations or historical CPI
 *
 * @returns {Promise<number>} Expected annual inflation rate (percentage)
 */
async function getInflationExpectation() {
  try {
    // Always fetch fresh inflation data - no caching
    // Query economic data from database (PCE inflation or CPI)
    const result = await db.query(`
      SELECT
        inflation_rate as rate
      FROM economic_data
      WHERE indicator = 'PCE' OR indicator = 'CPI'
      ORDER BY date DESC
      LIMIT 1
    `);

    let inflationRate = 3.0; // Default expectation

    if (result.rows && result.rows[0]) {
      inflationRate = parseFloat(result.rows[0].rate);
    }

    console.log(`✓ Inflation expectation: ${inflationRate.toFixed(2)}%`);
    return inflationRate;
  } catch (error) {
    console.warn('⚠️ Error fetching inflation expectation:', error.message);
    return 3.0; // Conservative default
  }
}

module.exports = {
  getDynamicRiskFreeRate,
  getMarketRegime,
  getInflationExpectation,
  getRegimeConstraints
};
