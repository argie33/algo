import axios from 'axios' 

// Get API configuration - exported for ServiceHealth
export const getApiConfig = () => {
  // Get API URL from environment variable (set by workflow)
  const apiUrl = import.meta.env.VITE_API_URL
  
  return {
    baseURL: apiUrl || 'http://localhost:3001', // Fallback for development
    isServerless: !!apiUrl, // Only true if VITE_API_URL is set
    apiUrl: apiUrl || 'http://localhost:3001',
    isConfigured: !!apiUrl,
    environment: import.meta.env.MODE,
    isDevelopment: import.meta.env.DEV,
    isProduction: import.meta.env.PROD,
    baseUrl: import.meta.env.BASE_URL,
    allEnvVars: import.meta.env
  }
}

// Create API instance that can be updated
let currentConfig = getApiConfig()

console.log('API Configuration:', {
  baseURL: currentConfig.baseURL,
  isServerless: currentConfig.isServerless,
  hostname: window.location.hostname,
  viteMode: import.meta.env.MODE,
  apiUrl: currentConfig.apiUrl
})

const api = axios.create({
  baseURL: currentConfig.baseURL,
  timeout: currentConfig.isServerless ? 45000 : 30000, // Longer timeout for Lambda cold starts
  headers: {
    'Content-Type': 'application/json',
  },
})

// Function to get current base URL
export const getCurrentBaseURL = () => {
  return currentConfig.baseURL
}

// Function to update API base URL dynamically
export const updateApiBaseUrl = (newUrl) => {
  currentConfig = { ...currentConfig, baseURL: newUrl, apiUrl: newUrl }
  api.defaults.baseURL = newUrl
  console.log('API base URL updated to:', newUrl)
}

// Retry configuration for Lambda cold starts
const retryRequest = async (error) => {
  const { config: requestConfig } = error
  
  if (!requestConfig || requestConfig.retryCount >= 3) {
    return Promise.reject(error)
  }
  
  requestConfig.retryCount = requestConfig.retryCount || 0
  requestConfig.retryCount += 1
    // Only retry on timeout or 5xx errors (common with Lambda cold starts)
  if (error.code === 'ECONNABORTED' || 
      (error.response && error.response.status >= 500)) {
    
    const delay = Math.pow(2, requestConfig.retryCount) * 1000 // Exponential backoff
    console.log(`Retrying request (attempt ${requestConfig.retryCount}) after ${delay}ms...`)
    
    await new Promise(resolve => setTimeout(resolve, delay))
    return api(requestConfig)
  }
  
  return Promise.reject(error)
}

// Request interceptor for logging and Lambda optimization
api.interceptors.request.use(
  (config) => {
    console.log(`API Request: ${config.method?.toUpperCase()} ${config.url}`)
      // Add headers for Lambda optimization
    if (config.isServerless) {
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

// Enhanced error handling and debugging
const handleApiError = (error, endpoint = 'unknown') => {
  console.error(`API Error on ${endpoint}:`, {
    message: error.message,
    response: error.response?.data,
    status: error.response?.status,
    config: error.config?.url,
    baseURL: error.config?.baseURL
  })
  
  // More specific error messages
  if (!error.response) {
    // Network error - can't reach server
    if (error.code === 'ECONNABORTED') {
      return `Request timeout on ${endpoint}. The server may be starting up.`
    } else {
      return `Network error on ${endpoint}. Check if API server is running and accessible.`
    }
  } else if (error.response.status >= 500) {
    return `Server error on ${endpoint}: ${error.response.data?.message || error.message}`
  } else if (error.response.status === 404) {
    return `Endpoint not found: ${endpoint}`
  } else {
    return `API error on ${endpoint}: ${error.response.data?.message || error.message}`
  }
}

// Response interceptor for error handling and retries
api.interceptors.response.use(
  (response) => {
    // Log Lambda execution details if available
    if (response.headers['x-amzn-requestid']) {
      console.log(`✅ Lambda Request ID: ${response.headers['x-amzn-requestid']}`)
    }
    console.log(`✅ API Response: ${response.config.method?.toUpperCase()} ${response.config.url} - ${response.status}`)
    return response
  },
  async (error) => {
    // Enhanced error logging
    const errorDetails = {
      message: error.message,
      status: error.response?.status,
      statusText: error.response?.statusText,
      data: error.response?.data,
      url: error.config?.url,
      method: error.config?.method,
      headers: error.config?.headers,
      timestamp: new Date().toISOString(),
      requestId: error.response?.headers?.['x-amzn-requestid'],
      code: error.code
    }
    
    console.error('❌ API Response Error:', errorDetails)
    
    // Handle specific error cases
    if (error.response?.status === 401) {
      console.warn('🔐 Unauthorized access detected')
    } else if (error.response?.status === 403) {
      console.warn('🚫 Forbidden - Check API permissions')
    } else if (error.response?.status === 404) {
      console.warn('🔍 Resource not found')
    } else if (error.response?.status === 429) {
      console.warn('⏳ Rate limit exceeded')
    } else if (error.response?.status >= 500 || error.code === 'ECONNABORTED') {
      console.error('🔥 Server error or timeout detected')
        // Attempt retry for serverless environments
      if (config.isServerless) {
        try {
          return await retryRequest(error)
        } catch (retryError) {
          console.error('💥 All retry attempts failed')
          return Promise.reject(retryError)
        }
      }
    } else if (error.code === 'ERR_NETWORK') {
      console.error('🌐 Network error - Check internet connection and API URL')
    }
    
    return Promise.reject(error)
  }
)


// Health check
export const healthCheck = async (queryParams = '') => {
  try {
    // Use current config to ensure we have the right baseURL
    const response = await api.get(`/health${queryParams}`, {
      baseURL: currentConfig.baseURL
    })
    console.log('Health check response:', response.data)
    return response // Return full response for consistency
  } catch (error) {
    console.error('Error in health check:', error)
    const errorMessage = handleApiError(error, 'health check')
    // Return a consistent error response structure
    return { 
      data: { 
        error: errorMessage,
        healthy: false,
        timestamp: new Date().toISOString()
      } 
    }
  }
}

// Market overview
// Market data - Updated to use proper market endpoints
export const getMarketOverview = async () => {
  try {
    const response = await api.get('/market/overview', {
      baseURL: currentConfig.baseURL
    })
    console.log('Market overview response:', response.data)
    return response // Return full response for consistency
  } catch (error) {
    console.error('Error fetching market overview:', error)
    const errorMessage = handleApiError(error, 'market overview')
    // Return a consistent error response structure
    return { 
      data: { 
        error: errorMessage
      } 
    }
  }
}

// Patch: Always return parsed data for all API methods
export const getMarketSentimentHistory = async (days = 30) => {
  try {
    const response = await api.get(`/market/sentiment/history?days=${days}`)
    return response.data
  } catch (error) {
    const errorMessage = handleApiError(error, 'get market sentiment history')
    return { data: [], error: errorMessage }
  }
}

export const getMarketSectorPerformance = async () => {
  try {
    const response = await api.get('/market/sectors/performance')
    return response.data
  } catch (error) {
    const errorMessage = handleApiError(error, 'get market sector performance')
    return { data: [], error: errorMessage }
  }
}

export const getMarketBreadth = async () => {
  try {
    const response = await api.get('/market/breadth')
    return response.data
  } catch (error) {
    const errorMessage = handleApiError(error, 'get market breadth')
    return { data: [], error: errorMessage }
  }
}

export const getEconomicIndicators = async (days = 90) => {
  try {
    const response = await api.get(`/market/economic?days=${days}`)
    return response.data
  } catch (error) {
    const errorMessage = handleApiError(error, 'get economic indicators')
    return { data: [], error: errorMessage }
  }
}

// Stocks - Updated to use optimized endpoints
export const getStocks = async (params = {}) => {
  try {
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
    
    const url = `/stocks?${queryParams.toString()}`
    console.log('Fetching stocks from:', url)
    
    const response = await api.get(url, {
      baseURL: currentConfig.baseURL
    })
    
    console.log('Stocks response:', response.data)
    return response // Return full response for consistency
  } catch (error) {
    console.error('Error fetching stocks:', error)
    const errorMessage = handleApiError(error, 'get stocks')
    // Return a consistent error response structure
    return { 
      data: { 
        data: [], 
        error: errorMessage
      } 
    }
  }
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

export const getStockPrices = async (ticker, timeframe = 'daily', limit = 100) => {
  try {
    const response = await api.get(`/stocks/${ticker}/prices?timeframe=${timeframe}&limit=${limit}`)
    return response.data
  } catch (error) {
    const errorMessage = handleApiError(error, 'get stock prices')
    return { data: [], error: errorMessage }
  }
}

export const getStockPricesRecent = async (ticker, limit = 30) => {
  try {
    const response = await api.get(`/stocks/${ticker}/price-recent?limit=${limit}`)
    return response.data
  } catch (error) {
    const errorMessage = handleApiError(error, 'get stock prices recent')
    return { data: [], error: errorMessage }
  }
}

export const getStockRecommendations = async (ticker) => {
  try {
    const response = await api.get(`/stocks/${ticker}/recommendations`)
    return response.data
  } catch (error) {
    const errorMessage = handleApiError(error, 'get stock recommendations')
    return { data: [], error: errorMessage }
  }
}

export const getSectors = async () => {
  try {
    const response = await api.get('/stocks/filters/sectors')
    return response.data
  } catch (error) {
    const errorMessage = handleApiError(error, 'get sectors')
    return { data: [], error: errorMessage }
  }
}

// Metrics
export const getValuationMetrics = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        queryParams.append(key, value)
      }
    })
    const response = await api.get(`/metrics/valuation?${queryParams.toString()}`)
    return response.data
  } catch (error) {
    console.error('Error fetching valuation metrics:', error)
    const errorMessage = handleApiError(error, 'get valuation metrics')
    return { data: [], error: errorMessage }
  }
}

export const getGrowthMetrics = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        queryParams.append(key, value)
      }
    })
    const response = await api.get(`/metrics/growth?${queryParams.toString()}`)
    return response.data
  } catch (error) {
    console.error('Error fetching growth metrics:', error)
    const errorMessage = handleApiError(error, 'get growth metrics')
    return { data: [], error: errorMessage }
  }
}

export const getDividendMetrics = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        queryParams.append(key, value)
      }
    })
    const response = await api.get(`/metrics/dividends?${queryParams.toString()}`)
    return response.data
  } catch (error) {
    console.error('Error fetching dividend metrics:', error)
    const errorMessage = handleApiError(error, 'get dividend metrics')
    return { data: [], error: errorMessage }
  }
}

export const getFinancialStrengthMetrics = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        queryParams.append(key, value)
      }
    })
    const response = await api.get(`/metrics/financial-strength?${queryParams.toString()}`)
    return response.data
  } catch (error) {
    console.error('Error fetching financial strength metrics:', error)
    const errorMessage = handleApiError(error, 'get financial strength metrics')
    return { data: [], error: errorMessage }
  }
}

// New method for stock screening with proper parameter handling
export const screenStocks = async (params) => {
  try {
    const response = await api.get(`/stocks?${params.toString()}`, {
      baseURL: currentConfig.baseURL
    })
    console.log('Screen stocks raw response:', response)
    if (!response.data || !Array.isArray(response.data.data)) {
      console.error('screenStocks: Unexpected response structure', response.data)
      throw new Error('Unexpected API response: missing data array')
    }
    return response.data
  } catch (error) {
    console.error('Error screening stocks:', error)
    const errorMessage = handleApiError(error, 'screen stocks')
    // Always return a consistent error structure
    return {
      data: [],
      error: errorMessage,
      count: 0,
      total: 0,
      timestamp: new Date().toISOString()
    }
  }
}

// Trading signals endpoints
export const getBuySignals = async () => {
  try {
    const response = await api.get('/signals/buy', {
      baseURL: currentConfig.baseURL
    })
    console.log('Buy signals response:', response.data)
    return response.data
  } catch (error) {
    console.error('Error fetching buy signals:', error)
    const errorMessage = handleApiError(error, 'get buy signals')
    return { data: [], error: errorMessage }
  }
}

export const getSellSignals = async () => {
  try {
    const response = await api.get('/signals/sell', {
      baseURL: currentConfig.baseURL
    })
    console.log('Sell signals response:', response.data)
    return response.data
  } catch (error) {
    console.error('Error fetching sell signals:', error)
    const errorMessage = handleApiError(error, 'get sell signals')
    return { data: [], error: errorMessage }
  }
}

// Earnings and analyst endpoints
export const getEarningsEstimates = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams()
    
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        queryParams.append(key, value)
      }
    })
    
    const response = await api.get(`/calendar/earnings-estimates?${queryParams.toString()}`, {
      baseURL: currentConfig.baseURL
    })
      console.log('Earnings estimates response:', response.data)
    return response.data
  } catch (error) {
    console.error('Error fetching earnings estimates:', error)
    const errorMessage = handleApiError(error, 'get earnings estimates')
    return { data: [], error: errorMessage }
  }
}

export const getEarningsHistory = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        queryParams.append(key, value)
      }
    })
    const response = await api.get(`/calendar/earnings-history?${queryParams.toString()}`)
    return response.data
  } catch (error) {
    console.error('Error fetching earnings history:', error)
    const errorMessage = handleApiError(error, 'get earnings history')
    return { data: [], error: errorMessage }
  }
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

// Financial statements endpoints
export const getBalanceSheet = async (ticker, period = 'annual') => {
  try {
    const url = `/financials/${ticker}/balance-sheet?period=${period}`
    console.log('Fetching balance sheet from:', url)
    
    const response = await api.get(url, {
      baseURL: currentConfig.baseURL
    })
    
    console.log('Balance sheet response:', response.data)
    return response // Return full response for consistency
  } catch (error) {
    console.error('Error fetching balance sheet:', error)
    const errorMessage = handleApiError(error, `get balance sheet for ${ticker}`)
    // Return a consistent error response structure
    return { 
      data: { 
        data: [], 
        error: errorMessage
      } 
    }
  }
}
export const getIncomeStatement = async (ticker, period = 'annual') => {
  try {
    const url = `/financials/${ticker}/income-statement?period=${period}`
    
    const response = await api.get(url, {
      baseURL: currentConfig.baseURL
    })
    
    console.log('Income statement response:', response.data)
    return response // Return full response for consistency
  } catch (error) {
    console.error('Error fetching income statement:', error)
    const errorMessage = handleApiError(error, `get income statement for ${ticker}`)
    // Return a consistent error response structure
    return { 
      data: { 
        data: [], 
        error: errorMessage
      } 
    }
  }
}

export const getCashFlowStatement = async (ticker, period = 'annual') => {
  try {
    const url = `/financials/${ticker}/cash-flow?period=${period}`
    
    const response = await api.get(url, {
      baseURL: currentConfig.baseURL
    })
    
    console.log('Cash flow response:', response.data)
    return response // Return full response for consistency
  } catch (error) {
    console.error('Error fetching cash flow statement:', error)
    const errorMessage = handleApiError(error, `get cash flow statement for ${ticker}`)
    // Return a consistent error response structure
    return { 
      data: { 
        data: [], 
        error: errorMessage
      } 
    }
  }
}
export const getFinancialStatements = (ticker, period = 'annual') => api.get(`/financials/${ticker}/financials?period=${period}`)

// Key metrics endpoint
export const getKeyMetrics = async (ticker) => {
  try {
    const url = `/financials/${ticker}/key-metrics`
    console.log('Fetching key metrics from:', url)
    
    const response = await api.get(url, {
      baseURL: currentConfig.baseURL
    })
    
    console.log('Key metrics response:', response.data)
    return response // Return full response for consistency
  } catch (error) {
    console.error('Error fetching key metrics:', error)
    const errorMessage = handleApiError(error, `get key metrics for ${ticker}`)
    // Return a consistent error response structure
    return { 
      data: { 
        data: null, 
        error: errorMessage
      } 
    }
  }
}

// Comprehensive financial data endpoint
export const getAllFinancialData = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        queryParams.append(key, value)
      }
    })
    const response = await api.get(`/financials/all?${queryParams.toString()}`)
    return response.data
  } catch (error) {
    const errorMessage = handleApiError(error, 'get all financial data')
    return { data: [], error: errorMessage }
  }
}

export const getFinancialMetrics = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        queryParams.append(key, value)
      }
    })
    const response = await api.get(`/financials/metrics?${queryParams.toString()}`)
    return response.data
  } catch (error) {
    const errorMessage = handleApiError(error, 'get financial metrics')
    return { data: [], error: errorMessage }
  }
}

// Technical data endpoint
export const getTechnicalData = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        queryParams.append(key, value)
      }
    })
    const response = await api.get(`/technical/data?${queryParams.toString()}`)
    return response.data
  } catch (error) {
    const errorMessage = handleApiError(error, 'get technical data')
    return { data: [], error: errorMessage }
  }
}

// Data validation summary endpoint
export const getDataValidationSummary = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        queryParams.append(key, value)
      }
    })
    const response = await api.get(`/data/validation/summary?${queryParams.toString()}`)
    return response.data
  } catch (error) {
    const errorMessage = handleApiError(error, 'get data validation summary')
    return { data: [], error: errorMessage }
  }
}

// EPS Revisions endpoint
export const getEpsRevisions = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        queryParams.append(key, value)
      }
    })
    const response = await api.get(`/eps/revisions?${queryParams.toString()}`)
    return response.data
  } catch (error) {
    const errorMessage = handleApiError(error, 'get eps revisions')
    return { data: [], error: errorMessage }
  }
}

// EPS Trend endpoint
export const getEpsTrend = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        queryParams.append(key, value)
      }
    })
    const response = await api.get(`/eps/trend?${queryParams.toString()}`)
    return response.data
  } catch (error) {
    const errorMessage = handleApiError(error, 'get eps trend')
    return { data: [], error: errorMessage }
  }
}

// Growth Estimates endpoint
export const getGrowthEstimates = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        queryParams.append(key, value)
      }
    })
    const response = await api.get(`/growth/estimates?${queryParams.toString()}`)
    return response.data
  } catch (error) {
    const errorMessage = handleApiError(error, 'get growth estimates')
    return { data: [], error: errorMessage }
  }
}

// NAAIM Data endpoint
export const getNaaimData = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        queryParams.append(key, value)
      }
    })
    const response = await api.get(`/market/naaim?${queryParams.toString()}`)
    return response.data
  } catch (error) {
    const errorMessage = handleApiError(error, 'get NAAIM data')
    return { data: [], error: errorMessage }
  }
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
  getStockPricesRecent,
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
  getKeyMetrics,
  getAllFinancialData,
  getFinancialMetrics,
  getEpsRevisions,
  getEpsTrend,
  getGrowthEstimates,
  getEconomicData,
  getNaaimData,
  getFearGreedData,
  getTechnicalData,
  getTechnicalSummary,
  getDataValidationSummary,
  getEarningsMetrics
}

// Test API Connection
export const testApiConnection = async (customUrl = null) => {
  try {    console.log('Testing API connection...')
    console.log('Current API URL:', currentConfig.baseURL)
    console.log('Custom URL:', customUrl)
    console.log('Environment:', import.meta.env.MODE)
    console.log('VITE_API_URL:', import.meta.env.VITE_API_URL)
      const testUrl = customUrl || currentConfig.baseURL
    const response = await api.get('/health?quick=true', {
      baseURL: testUrl,
      timeout: 10000
    })
    
    return {
      success: true,
      apiUrl: testUrl,
      status: response.status,
      data: response.data,
      message: 'API connection successful'
    }
  } catch (error) {
    console.error('API connection test failed:', error)
    
    return {
      success: false,
      apiUrl: customUrl || currentConfig.baseURL,
      error: error.message,
      details: {
        hasResponse: !!error.response,
        status: error.response?.status,
        statusText: error.response?.statusText,
        responseData: error.response?.data,
        code: error.code,
        isNetworkError: !error.response,
        configUrl: error.config?.url,
        fullUrl: (customUrl || currentConfig.baseURL) + '/health?quick=true'
      }    }
  }
}

// Diagnostic function for ServiceHealth
export const getDiagnosticInfo = () => {
  return {
    currentApiUrl: currentConfig.baseURL,
    axiosDefaultBaseUrl: api.defaults.baseURL,
    viteApiUrl: import.meta.env.VITE_API_URL,
    isConfigured: currentConfig.isConfigured,
    environment: import.meta.env.MODE,
    urlsMatch: currentConfig.baseURL === api.defaults.baseURL,
    timestamp: new Date().toISOString()
  }
}
