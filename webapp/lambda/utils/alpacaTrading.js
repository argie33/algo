/**
 * Alpaca Trading Initialization Helper
 *
 * Provides factory function for creating Alpaca trader instances
 */

const AlpacaService = require('./alpacaService');

/**
 * Initialize Alpaca trader with configured credentials
 * @param {Boolean} isPaper - Use paper trading (default: true)
 * @returns {AlpacaService|null} Alpaca service instance or null if not configured
 */
function initializeAlpacaTrader(isPaper = true) {
  try {
    // Use Alpaca's official naming convention first, fall back to alternate names for compatibility
    const apiKey = process.env.APCA_API_KEY_ID || process.env.ALPACA_API_KEY;
    const apiSecret = process.env.APCA_API_SECRET_KEY || process.env.ALPACA_API_SECRET || process.env.ALPACA_SECRET_KEY;

    if (!apiKey || !apiSecret) {
      console.warn('⚠️ Alpaca credentials not configured. Set APCA_API_KEY_ID and APCA_API_SECRET_KEY environment variables');
      return null;
    }

    return new AlpacaService(apiKey, apiSecret, isPaper);
  } catch (error) {
    console.error('Failed to initialize Alpaca trader:', error.message);
    return null;
  }
}

module.exports = {
  initializeAlpacaTrader,
  AlpacaService,
};
