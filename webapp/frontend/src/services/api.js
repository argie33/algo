import axios from 'axios' 

// Get API configuration - exported for ServiceHealth 
export const getApiConfig = () => {
  // Dynamic API URL resolution: runtime > build-time > fallback
  let runtimeApiUrl = (typeof window !== 'undefined' && window.__CONFIG__ && window.__CONFIG__.API_URL) ? window.__CONFIG__.API_URL : null;
  const apiUrl = runtimeApiUrl || import.meta.env.VITE_API_URL || 'http://localhost:3001';
  return {
    baseURL: apiUrl,
    isServerless: !!apiUrl && !apiUrl.includes('localhost'),
    apiUrl: apiUrl,
    isConfigured: !!apiUrl && !apiUrl.includes('localhost'),
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
  hostname: typeof window !== 'undefined' ? window.location.hostname : 'SSR',
  viteMode: import.meta.env.MODE,
  apiUrl: currentConfig.apiUrl
})

// Warn if API URL is fallback (localhost)
if (!currentConfig.apiUrl || currentConfig.apiUrl.includes('localhost')) {
  console.warn('[API CONFIG] Using fallback API URL:', currentConfig.baseURL + '\nSet window.__CONFIG__.API_URL at runtime or VITE_API_URL at build time to override.')
}

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
    const fullUrl = `${config.baseURL || api.defaults.baseURL}${config.url}`
    console.log(`[API REQUEST] ${config.method?.toUpperCase()} ${fullUrl}`)
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

// Enhanced diagnostics: Log every response's status and data
api.interceptors.response.use(
  (response) => {
    const fullUrl = `${response.config.baseURL || api.defaults.baseURL}${response.config.url}`
    console.log(`[API RESPONSE] ${response.status} from ${fullUrl}`, response.data)
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


// Market overview
export const getMarketOverview = async () => {
  try {
    const response = await api.get('/market/overview', {
      baseURL: currentConfig.baseURL
    })
    console.log('Market overview response:', response.data)
    return normalizeApiResponse(response.data)
  } catch (error) {
    console.error('Error fetching market overview:', error)
    const errorMessage = handleApiError(error, 'market overview')
    return { data: null, error: errorMessage }
  }
}

// Helper to unwrap { data: ... } if present, else return as-is
const unwrapApiResponse = (responseData) => {
  if (responseData && typeof responseData === 'object' && 'data' in responseData && Object.keys(responseData).length === 1) {
    return responseData.data
  }
  return responseData
}

// Patch: Always return parsed data for all API methods
export const getMarketSentimentHistory = async (days = 30) => {
  try {
    const response = await api.get(`/market/sentiment/history?days=${days}`)
    return normalizeApiResponse(response.data)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get market sentiment history')
    return { data: [], error: errorMessage }
  }
}

export const getMarketSectorPerformance = async () => {
  try {
    const response = await api.get('/market/sectors/performance')
    return normalizeApiResponse(response.data)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get market sector performance')
    return { data: [], error: errorMessage }
  }
}

export const getMarketBreadth = async () => {
  try {
    const response = await api.get('/market/breadth')
    return normalizeApiResponse(response.data)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get market breadth')
    return { data: [], error: errorMessage }
  }
}

export const getEconomicIndicators = async (days = 90) => {
  try {
    const response = await api.get(`/market/economic?days=${days}`)
    return normalizeApiResponse(response.data)
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
    return normalizeApiResponse(response.data)
  } catch (error) {
    console.error('Error fetching stocks:', error)
    const errorMessage = handleApiError(error, 'get stocks')
    return { data: [], error: errorMessage }
  }
}

// Quick stocks overview for initial page load
export const getStocksQuick = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        queryParams.append(key, value)
      }
    })
    const response = await api.get(`/stocks/quick/overview?${queryParams.toString()}`)
    return normalizeApiResponse(response.data)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get stocks quick')
    return { data: [], error: errorMessage }
  }
}

// Chunked stocks loading
export const getStocksChunk = async (chunkIndex = 0) => {
  try {
    const response = await api.get(`/stocks/chunk/${chunkIndex}`)
    return normalizeApiResponse(response.data)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get stocks chunk')
    return { data: [], error: errorMessage }
  }
}

// Full stocks data (use with caution)
export const getStocksFull = async (params = {}) => {
  try {
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
    const response = await api.get(`/stocks/full/data?${queryParams.toString()}`)
    return normalizeApiResponse(response.data)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get stocks full')
    return { data: [], error: errorMessage }
  }
}

export const getStock = async (ticker) => {
  try {
    const response = await api.get(`/stocks/${ticker}`)
    return normalizeApiResponse(response.data)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get stock')
    return { data: null, error: errorMessage }
  }
}

// New methods for StockDetail page
export const getStockProfile = async (ticker) => {
  try {
    const response = await api.get(`/stocks/${ticker}/profile`)
    return normalizeApiResponse(response.data)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get stock profile')
    return { data: null, error: errorMessage }
  }
}

export const getStockMetrics = async (ticker) => {
  try {
    const response = await api.get(`/stocks/${ticker}/metrics`)
    return normalizeApiResponse(response.data)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get stock metrics')
    return { data: null, error: errorMessage }
  }
}

export const getStockFinancials = async (ticker, type = 'income') => {
  try {
    const response = await api.get(`/stocks/${ticker}/financials?type=${type}`)
    return normalizeApiResponse(response.data)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get stock financials')
    return { data: null, error: errorMessage }
  }
}

export const getAnalystRecommendations = async (ticker) => {
  try {
    const response = await api.get(`/stocks/${ticker}/recommendations`)
    return normalizeApiResponse(response.data)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get analyst recommendations')
    return { data: [], error: errorMessage }
  }
}

export const getStockPrices = async (ticker, timeframe = 'daily', limit = 100) => {
  try {
    const response = await api.get(`/stocks/${ticker}/prices?timeframe=${timeframe}&limit=${limit}`)
    return normalizeApiResponse(response.data)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get stock prices')
    return { data: [], error: errorMessage }
  }
}

export const getStockPricesRecent = async (ticker, limit = 30) => {
  try {
    const response = await api.get(`/stocks/${ticker}/price-recent?limit=${limit}`)
    return normalizeApiResponse(response.data)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get stock prices recent')
    return { data: [], error: errorMessage }
  }
}

export const getStockRecommendations = async (ticker) => {
  try {
    const response = await api.get(`/stocks/${ticker}/recommendations`)
    return normalizeApiResponse(response.data)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get stock recommendations')
    return { data: [], error: errorMessage }
  }
}

export const getSectors = async () => {
  try {
    const response = await api.get('/stocks/filters/sectors')
    return normalizeApiResponse(response.data)
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
    return normalizeApiResponse(response.data)
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
    return normalizeApiResponse(response.data)
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
    return normalizeApiResponse(response.data)
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
    return normalizeApiResponse(response.data)
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
    return normalizeApiResponse(response.data)
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
    return normalizeApiResponse(response.data)
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
    return normalizeApiResponse(response.data)
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
    return normalizeApiResponse(response.data)
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
    return normalizeApiResponse(response.data)
  } catch (error) {
    console.error('Error fetching earnings history:', error)
    const errorMessage = handleApiError(error, 'get earnings history')
    return { data: [], error: errorMessage }
  }
}

// Ticker-based endpoints (wrap Axios promise for consistency)
export const getTickerEarningsEstimates = async (ticker) => {
  try {
    const response = await api.get(`/analysts/${ticker}/earnings-estimates`)
    return normalizeApiResponse(response.data)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get ticker earnings estimates')
    return { data: [], error: errorMessage }
  }
}

export const getTickerEarningsHistory = async (ticker) => {
  try {
    const response = await api.get(`/analysts/${ticker}/earnings-history`)
    return normalizeApiResponse(response.data)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get ticker earnings history')
    return { data: [], error: errorMessage }
  }
}

export const getTickerRevenueEstimates = async (ticker) => {
  try {
    const response = await api.get(`/analysts/${ticker}/revenue-estimates`)
    return normalizeApiResponse(response.data)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get ticker revenue estimates')
    return { data: [], error: errorMessage }
  }
}

export const getTickerEpsRevisions = async (ticker) => {
  try {
    const response = await api.get(`/analysts/${ticker}/eps-revisions`)
    return normalizeApiResponse(response.data)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get ticker eps revisions')
    return { data: [], error: errorMessage }
  }
}

export const getTickerEpsTrend = async (ticker) => {
  try {
    const response = await api.get(`/analysts/${ticker}/eps-trend`)
    return normalizeApiResponse(response.data)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get ticker eps trend')
    return { data: [], error: errorMessage }
  }
}

export const getTickerGrowthEstimates = async (ticker) => {
  try {
    const response = await api.get(`/analysts/${ticker}/growth-estimates`)
    return normalizeApiResponse(response.data)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get ticker growth estimates')
    return { data: [], error: errorMessage }
  }
}

export const getTickerAnalystRecommendations = async (ticker) => {
  try {
    const response = await api.get(`/analysts/${ticker}/recommendations`)
    return normalizeApiResponse(response.data)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get ticker analyst recommendations')
    return { data: [], error: errorMessage }
  }
}

export const getAnalystOverview = async (ticker) => {
  try {
    const response = await api.get(`/analysts/${ticker}/overview`)
    return normalizeApiResponse(response.data)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get analyst overview')
    return { data: null, error: errorMessage }
  }
}

// Financial statements endpoint (wrap for consistency)
export const getFinancialStatements = async (ticker, period = 'annual') => {
  try {
    const response = await api.get(`/financials/${ticker}/financials?period=${period}`)
    return normalizeApiResponse(response.data)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get financial statements')
    return { data: null, error: errorMessage }
  }
}

export const getIncomeStatement = async (ticker, period = 'annual') => {
  try {
    const url = `/financials/${ticker}/income-statement?period=${period}`
    const response = await api.get(url, {
      baseURL: currentConfig.baseURL
    })
    console.log('Income statement response:', response.data)
    return normalizeApiResponse(response.data)
  } catch (error) {
    console.error('Error fetching income statement:', error)
    const errorMessage = handleApiError(error, `get income statement for ${ticker}`)
    return { data: [], error: errorMessage }
  }
}

export const getCashFlowStatement = async (ticker, period = 'annual') => {
  try {
    const url = `/financials/${ticker}/cash-flow?period=${period}`
    const response = await api.get(url, {
      baseURL: currentConfig.baseURL
    })
    console.log('Cash flow response:', response.data)
    return normalizeApiResponse(response.data)
  } catch (error) {
    console.error('Error fetching cash flow statement:', error)
    const errorMessage = handleApiError(error, `get cash flow statement for ${ticker}`)
    return { data: [], error: errorMessage }
  }
}

export const getBalanceSheet = async (ticker, period = 'annual') => {
  try {
    const url = `/financials/${ticker}/balance-sheet?period=${period}`
    const response = await api.get(url, {
      baseURL: currentConfig.baseURL
    })
    console.log('Balance sheet response:', response.data)
    return normalizeApiResponse(response.data)
  } catch (error) {
    console.error('Error fetching balance sheet:', error)
    const errorMessage = handleApiError(error, `get balance sheet for ${ticker}`)
    return { data: [], error: errorMessage }
  }
}

// Key metrics endpoint
export const getKeyMetrics = async (ticker) => {
  try {
    const url = `/financials/${ticker}/key-metrics`
    console.log('Fetching key metrics from:', url)
    const response = await api.get(url, {
      baseURL: currentConfig.baseURL
    })
    console.log('Key metrics response:', response.data)
    return normalizeApiResponse(response.data)
  } catch (error) {
    console.error('Error fetching key metrics:', error)
    const errorMessage = handleApiError(error, `get key metrics for ${ticker}`)
    return { data: [], error: errorMessage }
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
    return normalizeApiResponse(response.data)
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
    return normalizeApiResponse(response.data)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get financial metrics')
    return { data: [], error: errorMessage }
  }
}

// Patch all API methods to use normalizeApiResponse
export const getTechnicalData = async (timeframe = 'daily', params = {}) => {
  try {
    const queryParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        queryParams.append(key, value)
      }
    })
    const response = await api.get(`/technical/${timeframe}?${queryParams.toString()}`)
    return normalizeApiResponse(response.data)
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
    return normalizeApiResponse(response.data)
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
    return normalizeApiResponse(response.data)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get eps revisions')
    return { data: [], error: errorMessage }
  }
}

export const getEpsTrend = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        queryParams.append(key, value)
      }
    })
    const response = await api.get(`/eps/trend?${queryParams.toString()}`)
    return normalizeApiResponse(response.data)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get eps trend')
    return { data: [], error: errorMessage }
  }
}

export const getGrowthEstimates = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        queryParams.append(key, value)
      }
    })
    const response = await api.get(`/growth/estimates?${queryParams.toString()}`)
    return normalizeApiResponse(response.data)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get growth estimates')
    return { data: [], error: errorMessage }
  }
}

export const getNaaimData = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        queryParams.append(key, value)
      }
    })
    const response = await api.get(`/market/naaim?${queryParams.toString()}`)
    return normalizeApiResponse(response.data)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get NAAIM data')
    return { data: [], error: errorMessage }
  }
}

export const getEconomicData = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        queryParams.append(key, value)
      }
    })
    const response = await api.get(`/economic/data?${queryParams.toString()}`)
    return normalizeApiResponse(response.data)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get economic data')
    return { data: [], error: errorMessage }
  }
}

export const getFearGreedData = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        queryParams.append(key, value)
      }
    })
    const response = await api.get(`/market/fear-greed?${queryParams.toString()}`)
    return normalizeApiResponse(response.data)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get fear & greed data')
    return { data: [], error: errorMessage }
  }
}

export const getTechnicalSummary = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        queryParams.append(key, value)
      }
    })
    const response = await api.get(`/technical/summary?${queryParams.toString()}`)
    return normalizeApiResponse(response.data)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get technical summary')
    return { data: [], error: errorMessage }
  }
}

export const getEarningsMetrics = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        queryParams.append(key, value)
      }
    })
    // Corrected endpoint path
    const response = await api.get(`/calendar/earnings-metrics?${queryParams.toString()}`)
    return normalizeApiResponse(response.data)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get earnings metrics')
    return { data: [], error: errorMessage }
  }
}

// Test API Connection
export const testApiConnection = async (customUrl = null) => {
  try {
    console.log('Testing API connection...')
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
      }
    }
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

// Database health (full details)
export const getDatabaseHealthFull = async () => {
  try {
    const response = await api.get('/health/database', {
      baseURL: currentConfig.baseURL
    })
    // Return the full response (healthSummary, tables, etc.)
    return { data: response.data }
  } catch (error) {
    const errorMessage = handleApiError(error, 'get database health')
    return { data: null, error: errorMessage }
  }
}

// Health check
export const healthCheck = async (queryParams = '') => {
  try {
    const response = await api.get(`/health${queryParams}`, {
      baseURL: currentConfig.baseURL
    })
    console.log('Health check response:', response.data)
    return {
      data: response.data,
      healthy: true,
      timestamp: new Date().toISOString()
    }
  } catch (error) {
    console.error('Error in health check:', error)
    const errorMessage = handleApiError(error, 'health check')
    return {
      data: null,
      error: errorMessage,
      healthy: false,
      timestamp: new Date().toISOString()
    }
  }
}

// --- Add this utility for consistent error handling ---
function handleApiError(error, context = '') {
  let message = 'An unexpected error occurred';
  if (error?.response?.data?.error) {
    message = error.response.data.error;
  } else if (error?.response?.data?.message) {
    message = error.response.data.message;
  } else if (error?.message) {
    message = error.message;
  }
  if (context) {
    return `${context}: ${message}`;
  }
  return message;
}

// Export healthCheck as a named export for compatibility with named imports
export { healthCheck };

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
  getEarningsMetrics,
  testApiConnection,
  getDiagnosticInfo,
  getApiConfig,
  getCurrentBaseURL,
  updateApiBaseUrl,
  getDatabaseHealthFull
}

