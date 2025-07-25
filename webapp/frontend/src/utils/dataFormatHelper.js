/**
 * Data Format Helper - Ensures consistent data handling across frontend
 * Handles both JSON API responses and HTML fallbacks
 */

/**
 * Extract data from API response with fallback handling
 * @param {any} response - Raw API response
 * @param {string} expectedFormat - 'json' | 'html' | 'auto'
 * @returns {Object} Normalized data object
 */
export const extractResponseData = (response, expectedFormat = 'auto') => {
  // Handle null/undefined
  if (!response) {
    console.warn('extractResponseData: No response data provided');
    return { success: false, data: null, error: 'No data received' };
  }

  // Auto-detect response format
  if (expectedFormat === 'auto') {
    if (typeof response === 'string' && response.includes('<!DOCTYPE html>')) {
      expectedFormat = 'html';
    } else {
      expectedFormat = 'json';
    }
  }

  // Handle HTML response (routing issue)
  if (expectedFormat === 'html' || (typeof response === 'string' && response.includes('<!DOCTYPE html>'))) {
    console.error('extractResponseData: Received HTML instead of JSON - API routing issue');
    return {
      success: false,
      data: null,
      error: 'API routing misconfiguration - receiving HTML instead of JSON',
      isRoutingError: true
    };
  }

  // Handle JSON response
  try {
    // Already parsed JSON object
    if (typeof response === 'object') {
      // Standard API response format
      if (response.hasOwnProperty('success')) {
        return {
          success: response.success,
          data: response.data || response,
          error: response.error || null,
          metadata: {
            timestamp: response.timestamp,
            pagination: response.pagination,
            dataSource: response.dataSource,
            provider: response.provider
          }
        };
      }
      
      // Raw data object
      return {
        success: true,
        data: response,
        error: null,
        metadata: {}
      };
    }

    // String that might be JSON
    if (typeof response === 'string') {
      const parsed = JSON.parse(response);
      return extractResponseData(parsed, 'json');
    }

    // Fallback
    return {
      success: true,
      data: response,
      error: null,
      metadata: {}
    };

  } catch (parseError) {
    console.error('extractResponseData: JSON parse error', parseError);
    return {
      success: false,
      data: null,
      error: 'Invalid JSON response format',
      parseError: parseError.message
    };
  }
};

/**
 * Validate and normalize array data
 * @param {any} data - Data to validate as array
 * @param {Array} fallback - Fallback array if data is invalid
 * @returns {Array} Valid array
 */
export const ensureArray = (data, fallback = []) => {
  if (Array.isArray(data)) return data;
  
  // Extract array from nested object
  if (data && typeof data === 'object') {
    if (Array.isArray(data.data)) return data.data;
    if (Array.isArray(data.results)) return data.results;
    if (Array.isArray(data.items)) return data.items;
  }
  
  console.warn('ensureArray: Data is not an array, using fallback', { data, fallback });
  return fallback;
};

/**
 * Extract paginated data with metadata
 * @param {any} response - API response
 * @returns {Object} Paginated data object
 */
export const extractPaginatedData = (response) => {
  const normalized = extractResponseData(response);
  
  return {
    ...normalized,
    data: ensureArray(normalized.data),
    pagination: normalized.metadata?.pagination || {
      page: 1,
      limit: 50,
      total: 0,
      totalPages: 1,
      hasNext: false,
      hasPrev: false
    }
  };
};

/**
 * Create consistent error object for UI display
 * @param {any} error - Error from API or processing
 * @returns {Object} Normalized error object
 */
export const normalizeError = (error) => {
  if (!error) return null;

  // String error
  if (typeof error === 'string') {
    return {
      message: error,
      type: 'generic',
      isRoutingError: error.includes('HTML instead of JSON'),
      canRetry: !error.includes('routing')
    };
  }

  // Error object
  if (error.message) {
    return {
      message: error.message,
      type: error.type || 'api_error',
      code: error.code,
      details: error.details,
      isRoutingError: error.isRoutingError || false,
      canRetry: !error.isRoutingError && error.type !== 'validation_error'
    };
  }

  return {
    message: 'Unknown error occurred',
    type: 'unknown',
    isRoutingError: false,
    canRetry: true
  };
};

/**
 * Handle API loading states with routing error detection
 * @param {boolean} loading - Loading state
 * @param {any} error - Error state
 * @param {any} data - Data state
 * @returns {Object} UI state object
 */
export const getUIState = (loading, error, data) => {
  const normalizedError = normalizeError(error);
  
  return {
    isLoading: loading,
    isError: !!normalizedError,
    isSuccess: !loading && !normalizedError && data !== null,
    isEmpty: !loading && !normalizedError && (!data || (Array.isArray(data) && data.length === 0)),
    error: normalizedError,
    showRoutingAlert: normalizedError?.isRoutingError || false,
    canRetry: normalizedError?.canRetry !== false
  };
};

/**
 * Create fallback data for development/demo purposes
 * @param {string} dataType - Type of data to create
 * @param {number} count - Number of items to create
 * @returns {Array|Object} Fallback data
 */
export const createFallbackData = (dataType, count = 5) => {
  const timestamp = new Date().toISOString();
  
  switch (dataType) {
    case 'stocks':
      return Array.from({ length: count }, (_, i) => ({
        symbol: `DEMO${i + 1}`,
        name: `Demo Stock ${i + 1}`,
        price: 100 + (Math.random() * 50),
        change: (Math.random() - 0.5) * 10,
        changePercent: (Math.random() - 0.5) * 0.1,
        volume: Math.floor(Math.random() * 1000000),
        lastUpdated: timestamp
      }));
      
    case 'portfolio':
      return {
        totalValue: 125000,
        dayChange: 2500,
        dayChangePercent: 0.02,
        holdings: Array.from({ length: count }, (_, i) => ({
          symbol: `HOLD${i + 1}`,
          shares: Math.floor(Math.random() * 100),
          avgCost: 50 + (Math.random() * 100),
          currentPrice: 60 + (Math.random() * 100),
          marketValue: Math.floor(Math.random() * 10000)
        })),
        lastUpdated: timestamp
      };
      
    case 'news':
      return Array.from({ length: count }, (_, i) => ({
        id: `news-${i + 1}`,
        title: `Market Update ${i + 1}`,
        summary: `This is a sample news article about market conditions...`,
        source: 'Demo News',
        publishedAt: timestamp,
        url: '#'
      }));

    case 'trading_signals':
      return Array.from({ length: count }, (_, i) => ({
        symbol: ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA'][i % 5],
        signal: i % 2 === 0 ? 'Buy' : 'Sell',
        date: timestamp,
        current_price: 100 + (Math.random() * 200),
        performance_percent: (Math.random() - 0.5) * 10,
        confidence: 0.7 + (Math.random() * 0.3),
        type: 'Technical'
      }));

    case 'market_sentiment':
      return {
        fearGreed: Math.floor(Math.random() * 100),
        naaim: Math.floor(Math.random() * 100),
        vix: 15 + (Math.random() * 20),
        status: ['Bullish', 'Bearish', 'Neutral'][Math.floor(Math.random() * 3)],
        aaii: {
          bullish: Math.floor(Math.random() * 50),
          bearish: Math.floor(Math.random() * 50),
          neutral: Math.floor(Math.random() * 50)
        }
      };

    case 'sectors':
      const sectors = ['Technology', 'Healthcare', 'Finance', 'Energy', 'Consumer', 'Industrial'];
      return sectors.map(sector => ({
        sector,
        performance: (Math.random() - 0.5) * 10
      }));

    case 'economic_indicators':
      return [
        { name: 'GDP Growth', value: 2.1 + (Math.random() * 2), trend: 'up' },
        { name: 'Inflation Rate', value: 3.0 + (Math.random() * 2), trend: 'down' },
        { name: 'Unemployment', value: 3.5 + (Math.random() * 2), trend: 'down' },
        { name: 'Interest Rate', value: 4.0 + (Math.random() * 2), trend: 'up' }
      ];

    case 'watchlist':
      return Array.from({ length: count }, (_, i) => ({
        symbol: ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'AMZN', 'META'][i % 7],
        price: 100 + (Math.random() * 200),
        change: (Math.random() - 0.5) * 10,
        score: 70 + Math.floor(Math.random() * 30)
      }));

    case 'activity':
      return Array.from({ length: count }, (_, i) => ({
        type: ['Buy', 'Sell', 'Dividend', 'Split'][i % 4],
        desc: `Sample trading activity ${i + 1}`,
        date: timestamp,
        amount: Math.floor(Math.random() * 5000)
      }));

    case 'calendar':
      return Array.from({ length: count }, (_, i) => ({
        event: `Economic Event ${i + 1}`,
        date: timestamp,
        impact: ['High', 'Medium', 'Low'][i % 3]
      }));

    case 'commodity_categories':
      return [
        {
          id: 'energy',
          name: 'Energy',
          description: 'Oil, gas, and energy commodities',
          commodities: ['crude-oil', 'natural-gas', 'heating-oil', 'gasoline'],
          weight: 0.35,
          performance: { '1d': 0.5, '1w': -2.1, '1m': 4.3, '3m': -8.7, '1y': 12.4 }
        },
        {
          id: 'precious-metals',
          name: 'Precious Metals',
          description: 'Gold, silver, platinum, and palladium',
          commodities: ['gold', 'silver', 'platinum', 'palladium'],
          weight: 0.25,
          performance: { '1d': -0.3, '1w': 1.8, '1m': -1.2, '3m': 5.6, '1y': 8.9 }
        },
        {
          id: 'base-metals',
          name: 'Base Metals',
          description: 'Copper, aluminum, zinc, and industrial metals',
          commodities: ['copper', 'aluminum', 'zinc', 'nickel', 'lead'],
          weight: 0.20,
          performance: { '1d': 1.2, '1w': 3.4, '1m': 2.8, '3m': -4.2, '1y': 15.7 }
        },
        {
          id: 'agriculture',
          name: 'Agriculture',
          description: 'Grains, livestock, and soft commodities',
          commodities: ['wheat', 'corn', 'soybeans', 'coffee', 'sugar', 'cotton'],
          weight: 0.15,
          performance: { '1d': -0.8, '1w': -1.5, '1m': 6.2, '3m': 12.1, '1y': -3.4 }
        },
        {
          id: 'livestock',
          name: 'Livestock',
          description: 'Cattle, hogs, and feeder cattle',
          commodities: ['live-cattle', 'feeder-cattle', 'lean-hogs'],
          weight: 0.05,
          performance: { '1d': 0.2, '1w': 2.1, '1m': -1.8, '3m': 7.3, '1y': 11.2 }
        }
      ];

    case 'commodity_prices':
      return [
        {
          symbol: 'CL',
          name: 'Crude Oil',
          category: 'energy',
          price: 78.45 + (Math.random() - 0.5) * 5,
          change: (Math.random() - 0.5) * 2,
          changePercent: (Math.random() - 0.5) * 3,
          unit: 'per barrel',
          currency: 'USD',
          volume: Math.floor(200000 + Math.random() * 100000),
          lastUpdated: timestamp
        },
        {
          symbol: 'GC',
          name: 'Gold',
          category: 'precious-metals',
          price: 2034.20 + (Math.random() - 0.5) * 50,
          change: (Math.random() - 0.5) * 10,
          changePercent: (Math.random() - 0.5) * 1,
          unit: 'per ounce',
          currency: 'USD',
          volume: Math.floor(80000 + Math.random() * 20000),
          lastUpdated: timestamp
        },
        {
          symbol: 'SI',
          name: 'Silver',
          category: 'precious-metals',
          price: 24.67 + (Math.random() - 0.5) * 2,
          change: (Math.random() - 0.5) * 0.5,
          changePercent: (Math.random() - 0.5) * 2,
          unit: 'per ounce',
          currency: 'USD',
          volume: Math.floor(30000 + Math.random() * 10000),
          lastUpdated: timestamp
        },
        {
          symbol: 'HG',
          name: 'Copper',
          category: 'base-metals',
          price: 3.89 + (Math.random() - 0.5) * 0.2,
          change: (Math.random() - 0.5) * 0.1,
          changePercent: (Math.random() - 0.5) * 2,
          unit: 'per pound',
          currency: 'USD',
          volume: Math.floor(60000 + Math.random() * 20000),
          lastUpdated: timestamp
        },
        {
          symbol: 'NG',
          name: 'Natural Gas',
          category: 'energy',
          price: 2.87 + (Math.random() - 0.5) * 0.3,
          change: (Math.random() - 0.5) * 0.2,
          changePercent: (Math.random() - 0.5) * 5,
          unit: 'per MMBtu',
          currency: 'USD',
          volume: Math.floor(100000 + Math.random() * 50000),
          lastUpdated: timestamp
        },
        {
          symbol: 'ZW',
          name: 'Wheat',
          category: 'agriculture',
          price: 6.45 + (Math.random() - 0.5) * 0.5,
          change: (Math.random() - 0.5) * 0.2,
          changePercent: (Math.random() - 0.5) * 3,
          unit: 'per bushel',
          currency: 'USD',
          volume: Math.floor(40000 + Math.random() * 20000),
          lastUpdated: timestamp
        }
      ].slice(0, count);

    case 'commodity_summary':
      return {
        overview: {
          totalMarketCap: 4.2e12,
          totalVolume: 1.8e9,
          activeContracts: 125847,
          tradingSession: 'open'
        },
        performance: {
          '1d': {
            gainers: 18,
            losers: 12,
            unchanged: 3,
            topGainer: { symbol: 'HG', name: 'Copper', change: 1.17 },
            topLoser: { symbol: 'NG', name: 'Natural Gas', change: -4.02 }
          }
        },
        sectors: [
          { name: 'Energy', weight: 0.35, change: 0.62, volume: 8.9e8 },
          { name: 'Precious Metals', weight: 0.25, change: -0.15, volume: 3.2e8 }
        ]
      };
      
    default:
      return [];
  }
};

export default {
  extractResponseData,
  ensureArray,
  extractPaginatedData,
  normalizeError,
  getUIState,
  createFallbackData
};