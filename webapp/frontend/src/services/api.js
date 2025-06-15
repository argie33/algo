import axios from 'axios'

// API Gateway/Lambda configuration
const API_BASE_URL = import.meta.env.VITE_API_URL || '/api'
const IS_SERVERLESS = import.meta.env.VITE_SERVERLESS === 'true'

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: IS_SERVERLESS ? 45000 : 30000, // Longer timeout for Lambda cold starts
  headers: {
    'Content-Type': 'application/json',
  },
})

// Retry configuration for Lambda cold starts
const retryRequest = async (error) => {
  const { config } = error
  
  if (!config || config.retryCount >= 3) {
    return Promise.reject(error)
  }
  
  config.retryCount = config.retryCount || 0
  config.retryCount += 1
  
  // Only retry on timeout or 5xx errors (common with Lambda cold starts)
  if (error.code === 'ECONNABORTED' || 
      (error.response && error.response.status >= 500)) {
    
    const delay = Math.pow(2, config.retryCount) * 1000 // Exponential backoff
    console.log(`Retrying request (attempt ${config.retryCount}) after ${delay}ms...`)
    
    await new Promise(resolve => setTimeout(resolve, delay))
    return api(config)
  }
  
  return Promise.reject(error)
}

// Request interceptor for logging and Lambda optimization
api.interceptors.request.use(
  (config) => {
    console.log(`API Request: ${config.method?.toUpperCase()} ${config.url}`)
    
    // Add headers for Lambda optimization
    if (IS_SERVERLESS) {
      config.headers['X-Lambda-Request'] = 'true'
      config.headers['X-Request-Time'] = new Date().toISOString()
    }
    
    return config
  },
  (error) => {
    console.error('API Request Error:', error)
    return Promise.reject(error)
  }
)

// Response interceptor for error handling and retries
api.interceptors.response.use(
  (response) => {
    // Log Lambda execution details if available
    if (response.headers['x-amzn-requestid']) {
      console.log(`Lambda Request ID: ${response.headers['x-amzn-requestid']}`)
    }
    return response
  },
  async (error) => {
    console.error('API Response Error:', error.response?.data || error.message)
    
    // Handle specific error cases
    if (error.response?.status === 401) {
      console.warn('Unauthorized access detected')
    } else if (error.response?.status === 429) {
      console.warn('Rate limit exceeded')
    } else if (error.response?.status >= 500 || error.code === 'ECONNABORTED') {
      console.error('Server error or timeout detected')
      
      // Attempt retry for serverless environments
      if (IS_SERVERLESS) {
        try {
          return await retryRequest(error)
        } catch (retryError) {
          console.error('All retry attempts failed')
          return Promise.reject(retryError)
        }
      }
    }
    
    return Promise.reject(error)
  }
)

// Health check
export const healthCheck = () => api.get('/health')

// Market overview
// Market data - Updated to use proper market endpoints
export const getMarketOverview = () => api.get('/market/overview')
export const getMarketSentimentHistory = (days = 30) => api.get(`/market/sentiment/history?days=${days}`)
export const getMarketSectorPerformance = () => api.get('/market/sectors/performance')
export const getMarketBreadth = () => api.get('/market/breadth')
export const getEconomicIndicators = (days = 90) => api.get(`/market/economic?days=${days}`)

// Stocks - Updated to use optimized endpoints
export const getStocks = (params = {}) => {
  const queryParams = new URLSearchParams()
  
  // Use smaller default limit to prevent white screen
  if (!params.limit) {
    params.limit = 10
  }
  
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      queryParams.append(key, value)
    }
  })
  
  return api.get(`/stocks?${queryParams.toString()}`)
}

// Quick stocks overview for initial page load
export const getStocksQuick = (params = {}) => {
  const queryParams = new URLSearchParams()
  
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      queryParams.append(key, value)
    }
  })
  
  return api.get(`/stocks/quick/overview?${queryParams.toString()}`)
}

// Chunked stocks loading
export const getStocksChunk = (chunkIndex = 0) => {
  return api.get(`/stocks/chunk/${chunkIndex}`)
}

// Full stocks data (use with caution)
export const getStocksFull = (params = {}) => {
  const queryParams = new URLSearchParams()
  
  // Force small limit for safety
  if (!params.limit || params.limit > 10) {
    params.limit = 5
    console.warn('Stocks limit reduced to 5 for performance')
  }
  
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      queryParams.append(key, value)
    }
  })
  
  return api.get(`/stocks/full/data?${queryParams.toString()}`)
}

export const getStock = (ticker) => api.get(`/stocks/${ticker}`)

// New methods for StockDetail page
export const getStockProfile = (ticker) => api.get(`/stocks/${ticker}/profile`)

export const getStockMetrics = (ticker) => api.get(`/stocks/${ticker}/metrics`)

export const getStockFinancials = (ticker, type = 'income') => 
  api.get(`/stocks/${ticker}/financials?type=${type}`)

export const getAnalystRecommendations = (ticker) => 
  api.get(`/stocks/${ticker}/recommendations`)

export const getStockPrices = (ticker, timeframe = 'daily', limit = 100) => 
  api.get(`/stocks/${ticker}/prices?timeframe=${timeframe}&limit=${limit}`)

export const getStockRecommendations = (ticker) => 
  api.get(`/stocks/${ticker}/recommendations`)

export const getSectors = () => api.get('/stocks/filters/sectors')

// Metrics
export const getValuationMetrics = (params = {}) => {
  const queryParams = new URLSearchParams()
  
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      queryParams.append(key, value)
    }
  })
  
  return api.get(`/metrics/valuation?${queryParams.toString()}`)
}

export const getGrowthMetrics = (params = {}) => {
  const queryParams = new URLSearchParams()
  
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      queryParams.append(key, value)
    }
  })
  
  return api.get(`/metrics/growth?${queryParams.toString()}`)
}

export const getDividendMetrics = (params = {}) => {
  const queryParams = new URLSearchParams()
  
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      queryParams.append(key, value)
    }
  })
  
  return api.get(`/metrics/dividends?${queryParams.toString()}`)
}

export const getFinancialStrengthMetrics = (params = {}) => {
  const queryParams = new URLSearchParams()
  
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      queryParams.append(key, value)
    }
  })
    return api.get(`/metrics/financial-strength?${queryParams.toString()}`)
}

// New method for stock screening with proper parameter handling
export const screenStocks = (params) => {
  return api.get(`/stocks/screen?${params.toString()}`)
}

// Trading signals endpoints
export const getBuySignals = () => {
  return api.get('/signals/buy')
}

export const getSellSignals = () => {
  return api.get('/signals/sell')
}

// Earnings and analyst endpoints
export const getEarningsEstimates = (params = {}) => {
  const queryParams = new URLSearchParams()
  
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      queryParams.append(key, value)
    }
  })
  
  return api.get(`/calendar/earnings-estimates?${queryParams.toString()}`)
}

export const getEarningsHistory = (params = {}) => {
  const queryParams = new URLSearchParams()
  
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      queryParams.append(key, value)
    }
  })
  
  return api.get(`/calendar/earnings-history?${queryParams.toString()}`)
}

export const getTickerEarningsEstimates = (ticker) => 
  api.get(`/analysts/${ticker}/earnings-estimates`)

export const getTickerEarningsHistory = (ticker) => 
  api.get(`/analysts/${ticker}/earnings-history`)

export const getTickerRevenueEstimates = (ticker) => 
  api.get(`/analysts/${ticker}/revenue-estimates`)

export const getTickerEpsRevisions = (ticker) => api.get(`/analysts/${ticker}/eps-revisions`)
export const getTickerEpsTrend = (ticker) => api.get(`/analysts/${ticker}/eps-trend`)
export const getTickerGrowthEstimates = (ticker) => api.get(`/analysts/${ticker}/growth-estimates`)
export const getTickerAnalystRecommendations = (ticker) => api.get(`/analysts/${ticker}/recommendations`)
export const getAnalystOverview = (ticker) => api.get(`/analysts/${ticker}/overview`)

// General analyst data endpoints (for market-wide analysis)
export const getEpsRevisions = (params = {}) => {
  const queryParams = new URLSearchParams()
  
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      queryParams.append(key, value)
    }
  })
  
  return api.get(`/analysts/eps-revisions?${queryParams.toString()}`)
}

export const getEpsTrend = (params = {}) => {
  const queryParams = new URLSearchParams()
  
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      queryParams.append(key, value)
    }
  })
  
  return api.get(`/analysts/eps-trend?${queryParams.toString()}`)
}

export const getGrowthEstimates = (params = {}) => {
  const queryParams = new URLSearchParams()
  
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      queryParams.append(key, value)
    }
  })
  
  return api.get(`/analysts/growth-estimates?${queryParams.toString()}`)
}

// Economic and market data endpoints
export const getEconomicData = (params = {}) => {
  const queryParams = new URLSearchParams()
  
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      queryParams.append(key, value)
    }
  })
  
  return api.get(`/market/economic-data?${queryParams.toString()}`)
}

export const getNaaimData = (params = {}) => {
  const queryParams = new URLSearchParams()
  
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      queryParams.append(key, value)
    }
  })
  
  return api.get(`/market/naaim?${queryParams.toString()}`)
}

export const getFearGreedData = (params = {}) => {
  const queryParams = new URLSearchParams()
  
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      queryParams.append(key, value)
    }
  })
  
  return api.get(`/market/fear-greed?${queryParams.toString()}`)
}

// Technical analysis endpoints
export const getTechnicalData = (params = {}) => {
  const queryParams = new URLSearchParams()
  
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      queryParams.append(key, value)
    }
  })
  
  return api.get(`/technical/data?${queryParams.toString()}`)
}

export const getTechnicalSummary = (params = {}) => {
  const queryParams = new URLSearchParams()
  
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      queryParams.append(key, value)
    }
  })
  
  return api.get(`/technical/summary?${queryParams.toString()}`)
}

export const getTechnicalChunk = (params = {}) => {
  const queryParams = new URLSearchParams()
  
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      queryParams.append(key, value)
    }
  })
  
  return api.get(`/technical/chunk?${queryParams.toString()}`)
}

export const getTechnicalFull = (params = {}) => {
  const queryParams = new URLSearchParams()
  
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      queryParams.append(key, value)
    }
  })
  
  return api.get(`/technical/full?${queryParams.toString()}`)
}

// Export all methods as a default object for easier importing
export default {
  healthCheck,
  getMarketOverview,
  getMarketSentimentHistory,
  getMarketSectorPerformance,
  getMarketBreadth,
  getEconomicIndicators,
  getStocks,
  getStocksQuick,
  getStocksChunk,
  getStocksFull,
  getStock,
  getStockProfile,
  getStockMetrics,
  getStockFinancials,
  getAnalystRecommendations,
  getStockPrices,
  getStockRecommendations,
  getSectors,
  getValuationMetrics,
  getGrowthMetrics,
  getDividendMetrics,
  getFinancialStrengthMetrics,
  screenStocks,
  getBuySignals,
  getSellSignals,
  getEarningsEstimates,
  getEarningsHistory,
  getTickerEarningsEstimates,
  getTickerEarningsHistory,
  getTickerRevenueEstimates,
  getTickerEpsRevisions,
  getTickerEpsTrend,
  getTickerGrowthEstimates,
  getTickerAnalystRecommendations,
  getAnalystOverview,
  getBalanceSheet,
  getIncomeStatement,
  getCashFlowStatement,
  getFinancialStatements,
  getEpsRevisions,
  getEpsTrend,
  getGrowthEstimates,
  getEconomicData,
  getNaaimData,
  getFearGreedData,
  getTechnicalData,
  getTechnicalSummary,
  getTechnicalChunk,
  getTechnicalFull,
  getAllFinancialData,
  getFinancialMetrics,
  getDataValidationSummary
}
