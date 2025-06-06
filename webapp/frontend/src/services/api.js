import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api'

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor for logging
api.interceptors.request.use(
  (config) => {
    console.log(`API Request: ${config.method?.toUpperCase()} ${config.url}`)
    return config
  },
  (error) => {
    console.error('API Request Error:', error)
    return Promise.reject(error)
  }
)

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => {
    return response
  },
  (error) => {
    console.error('API Response Error:', error.response?.data || error.message)
    
    if (error.response?.status === 401) {
      // Handle unauthorized access
      console.warn('Unauthorized access detected')
    } else if (error.response?.status >= 500) {
      // Handle server errors
      console.error('Server error detected')
    }
    
    return Promise.reject(error)
  }
)

// Health check
export const healthCheck = () => api.get('/health')

// Market overview
export const getMarketOverview = () => api.get('/metrics/overview')

// Stocks
export const getStocks = (params = {}) => {
  const queryParams = new URLSearchParams()
  
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      queryParams.append(key, value)
    }
  })
  
  return api.get(`/stocks?${queryParams.toString()}`)
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

export const runStockScreener = (params = {}) => {
  const queryParams = new URLSearchParams()
  
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      queryParams.append(key, value)
    }
  })
  
  return api.get(`/metrics/screener?${queryParams.toString()}`)
}

// New method for stock screening with proper parameter handling
export const screenStocks = (params) => {
  return api.get(`/stocks/screen?${params.toString()}`)
}

// Export all methods as a default object for easier importing
export default {
  healthCheck,
  getMarketOverview,
  getStocks,
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
  runStockScreener,
  screenStocks
}
