/**
 * Utility to get the correct path for comprehensive market data
 * Works on both Windows and Linux/Unix systems
 */

const path = require('path');
const os = require('os');

function getMarketDataPath() {
  if (process.platform === 'win32') {
    return path.join(process.env.TEMP || os.tmpdir(), 'comprehensive_market_data.json');
  }
  return '/tmp/comprehensive_market_data.json';
}

module.exports = {
  getMarketDataPath
};
