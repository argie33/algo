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
    const apiKey = process.env.ALPACA_API_KEY || process.env.APCA_API_KEY_ID;
    const apiSecret = process.env.ALPACA_SECRET_KEY || process.env.APCA_API_SECRET_KEY;

    if (!apiKey || !apiSecret) {
      console.warn('⚠️ Alpaca credentials not configured (ALPACA_API_KEY and ALPACA_SECRET_KEY required)');
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
