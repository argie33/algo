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

// Export the api instance for direct use
export { api }

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

// Helper to normalize API responses - return Axios response.data directly
function normalizeApiResponse(response, expectArray = true) {
  console.log('normalizeApiResponse input:', response)
  
  // If response is null or undefined, return appropriate default
  if (response == null) {
    console.log('normalizeApiResponse: null/undefined input, returning default')
    return expectArray ? [] : {};
  }

  // If response is an Axios response object, extract the data directly
  if (response && typeof response === 'object' && 'data' in response && ('status' in response || 'headers' in response)) {
    console.log('normalizeApiResponse: Axios response detected, returning data directly:', response.data)
    return response.data;
  }

  // If response is already the data (not an Axios response), return as-is
  if (Array.isArray(response) || (typeof response === 'object' && !('status' in response) && !('headers' in response))) {
    console.log('normalizeApiResponse: direct data, returning as-is')
    return response;
  }

  // Fallback to appropriate default
  console.log('normalizeApiResponse: fallback to default')
  return expectArray ? [] : {};
}

// --- PATCH: Wrap all API methods with normalizeApiResponse ---
// Market overview
export const getMarketOverview = async () => {
  try {
    const response = await api.get('/market/overview', {
      baseURL: currentConfig.baseURL
    })
    console.log('Market overview raw response:', response)
    console.log('Market overview response data:', response.data)
    const normalized = normalizeApiResponse(response, false) // Market overview is an object
    console.log('Market overview normalized:', normalized)
    return normalized
  } catch (error) {
    console.error('Error fetching market overview:', error)
    const errorMessage = handleApiError(error, 'market overview')
    return { error: errorMessage }
  }
}

export const getMarketSentimentHistory = async (days = 30) => {
  try {
    const response = await api.get(`/market/sentiment/history?days=${days}`)
    return normalizeApiResponse(response, true) // Array of historical data
  } catch (error) {
    const errorMessage = handleApiError(error, 'get market sentiment history')
    return { error: errorMessage }
  }
}

export const getMarketSectorPerformance = async () => {
  try {
    const response = await api.get('/market/sectors/performance')
    return normalizeApiResponse(response, true) // Array of sector data
  } catch (error) {
    const errorMessage = handleApiError(error, 'get market sector performance')
    return { error: errorMessage }
  }
}

export const getMarketBreadth = async () => {
  try {
    const response = await api.get('/market/breadth')
    return normalizeApiResponse(response, false) // Market breadth is an object
  } catch (error) {
    const errorMessage = handleApiError(error, 'get market breadth')
    return { error: errorMessage }
  }
}

export const getEconomicIndicators = async (days = 90) => {
  try {
    const response = await api.get(`/market/economic?days=${days}`)
    return normalizeApiResponse(response, true) // Array of economic data
  } catch (error) {
    const errorMessage = handleApiError(error, 'get economic indicators')
    return { error: errorMessage }
  }
}

// Stocks - Updated to use optimized endpoints
export const getStocks = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams()    // Use smaller default limit to prevent white screen
    if (!params.limit) {
      params.limit = 10
    }
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        queryParams.append(key, value)
      }
    });
    const url = `/stocks?${queryParams.toString()}`
    console.log('Fetching stocks from:', url)
    const response = await api.get(url, {
      baseURL: currentConfig.baseURL
    });
    console.log('Raw Axios Response:', response)
    console.log('Response data:', response.data)
    console.log('Response status:', response.status);
    console.log('Stocks response structure:', {
      hasSuccess: 'success' in response.data,
      hasData: 'data' in response.data,
      hasPagination: 'pagination' in response.data,
      hasMetadata: 'metadata' in response.data,
      dataLength: response.data.data?.length || 0
    })
    
    // The backend returns {success: true, data: [...], pagination: {...}, metadata: {...}}
    // We need to return the entire response structure, not just the data array
    return response.data
  } catch (error) {
    console.error('Error fetching stocks:', error)
    const errorMessage = handleApiError(error, 'get stocks')
    return {
      success: false,
      data: [],
      error: errorMessage,
      pagination: { page: 1, limit: 10, total: 0, totalPages: 0, hasNext: false, hasPrev: false },
      metadata: { timestamp: new Date().toISOString() }
    }
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
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get stocks quick')
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

// Chunked stocks loading
export const getStocksChunk = async (chunkIndex = 0) => {
  try {
    const response = await api.get(`/stocks/chunk/${chunkIndex}`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get stocks chunk')
    return normalizeApiResponse({ data: [], error: errorMessage })
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
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get stocks full')
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

export const getStock = async (ticker) => {
  try {
    const response = await api.get(`/stocks/${ticker}`)
    return normalizeApiResponse(response, false) // Single stock is an object
  } catch (error) {
    const errorMessage = handleApiError(error, 'get stock')
    return normalizeApiResponse({ error: errorMessage }, false)
  }
}

// New methods for StockDetail page
export const getStockProfile = async (ticker) => {
  try {
    const response = await api.get(`/stocks/${ticker}/profile`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get stock profile')
    return normalizeApiResponse({ data: null, error: errorMessage })
  }
}

export const getStockMetrics = async (ticker) => {
  try {
    const response = await api.get(`/stocks/${ticker}/metrics`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get stock metrics')
    return normalizeApiResponse({ data: null, error: errorMessage })
  }
}

export const getStockFinancials = async (ticker, type = 'income') => {
  try {
    const response = await api.get(`/stocks/${ticker}/financials?type=${type}`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get stock financials')
    return normalizeApiResponse({ data: null, error: errorMessage })
  }
}

export const getAnalystRecommendations = async (ticker) => {
  try {
    const response = await api.get(`/stocks/${ticker}/recommendations`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get analyst recommendations')
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

export const getStockPrices = async (ticker, timeframe = 'daily', limit = 100) => {
  try {
    const response = await api.get(`/stocks/${ticker}/prices?timeframe=${timeframe}&limit=${limit}`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get stock prices')
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

export const getStockPricesRecent = async (ticker, limit = 30) => {
  try {
    const response = await api.get(`/stocks/${ticker}/price-recent?limit=${limit}`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get stock prices recent')
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

export const getStockRecommendations = async (ticker) => {
  try {
    const response = await api.get(`/stocks/${ticker}/recommendations`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get stock recommendations')
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

export const getSectors = async () => {
  try {
    const response = await api.get('/stocks/filters/sectors')
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get sectors')
    return normalizeApiResponse({ data: [], error: errorMessage })
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
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get valuation metrics')
    return normalizeApiResponse({ data: [], error: errorMessage })
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
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get growth metrics')
    return normalizeApiResponse({ data: [], error: errorMessage })
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
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get dividend metrics')
    return normalizeApiResponse({ data: [], error: errorMessage })
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
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get financial strength metrics')
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

// New method for stock screening with proper parameter handling
export const screenStocks = async (params) => {
  try {
    const url = `/stocks?${params.toString()}`
    console.log('Screen stocks URL:', url)
    const response = await api.get(url, {
      baseURL: currentConfig.baseURL
    })
    console.log('Screen stocks raw response:', response)
    console.log('Screen stocks response data:', response.data)
    
    // Return the response.data directly since the backend returns the correct structure
    // { success: true, data: [...], pagination: {...} }
    return response.data
  } catch (error) {
    console.error('Error screening stocks:', error)
    const errorMessage = handleApiError(error, 'screen stocks')
    return {
      success: false,
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
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get buy signals')
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

export const getSellSignals = async () => {
  try {
    const response = await api.get('/signals/sell', {
      baseURL: currentConfig.baseURL
    })
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get sell signals')
    return normalizeApiResponse({ data: [], error: errorMessage })
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
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get earnings estimates')
    return normalizeApiResponse({ data: [], error: errorMessage })
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
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get earnings history')
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

// Ticker-based endpoints (wrap Axios promise for consistency)
export const getTickerEarningsEstimates = async (ticker) => {
  try {
    const response = await api.get(`/analysts/${ticker}/earnings-estimates`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get ticker earnings estimates')
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

export const getTickerEarningsHistory = async (ticker) => {
  try {
    const response = await api.get(`/analysts/${ticker}/earnings-history`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get ticker earnings history')
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

export const getTickerRevenueEstimates = async (ticker) => {
  try {
    const response = await api.get(`/analysts/${ticker}/revenue-estimates`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get ticker revenue estimates')
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

export const getTickerEpsRevisions = async (ticker) => {
  try {
    const response = await api.get(`/analysts/${ticker}/eps-revisions`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get ticker eps revisions')
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

export const getTickerEpsTrend = async (ticker) => {
  try {
    const response = await api.get(`/analysts/${ticker}/eps-trend`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get ticker eps trend')
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

export const getTickerGrowthEstimates = async (ticker) => {
  try {
    const response = await api.get(`/analysts/${ticker}/growth-estimates`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get ticker growth estimates')
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

export const getTickerAnalystRecommendations = async (ticker) => {
  try {
    const response = await api.get(`/analysts/${ticker}/recommendations`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get ticker analyst recommendations')
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

export const getAnalystOverview = async (ticker) => {
  try {
    const response = await api.get(`/analysts/${ticker}/overview`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get analyst overview')
    return normalizeApiResponse({ data: null, error: errorMessage })
  }
}

// Financial statements endpoint (wrap for consistency)
export const getFinancialStatements = async (ticker, period = 'annual') => {
  try {
    const response = await api.get(`/financials/${ticker}/financials?period=${period}`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get financial statements')
    return normalizeApiResponse({ data: null, error: errorMessage })
  }
}

export const getIncomeStatement = async (ticker, period = 'annual') => {
  try {
    const url = `/financials/${ticker}/income-statement?period=${period}`
    const response = await api.get(url, {
      baseURL: currentConfig.baseURL
    })
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, `get income statement for ${ticker}`)
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

export const getCashFlowStatement = async (ticker, period = 'annual') => {
  try {
    const url = `/financials/${ticker}/cash-flow?period=${period}`
    const response = await api.get(url, {
      baseURL: currentConfig.baseURL
    })
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, `get cash flow statement for ${ticker}`)
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

export const getBalanceSheet = async (ticker, period = 'annual') => {
  try {
    const url = `/financials/${ticker}/balance-sheet?period=${period}`
    const response = await api.get(url, {
      baseURL: currentConfig.baseURL
    })
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, `get balance sheet for ${ticker}`)
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

export const getKeyMetrics = async (ticker) => {
  try {
    const url = `/financials/${ticker}/key-metrics`
    const response = await api.get(url, {
      baseURL: currentConfig.baseURL
    })
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, `get key metrics for ${ticker}`)
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

export const getAllFinancialData = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        queryParams.append(key, value)
      }
    })
    const response = await api.get(`/financials/all?${queryParams.toString()}`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get all financial data')
    return normalizeApiResponse({ data: [], error: errorMessage })
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
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get financial metrics')
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

// Patch all API methods to always return normalizeApiResponse 
export const getTechnicalData = async (timeframe = 'daily', params = {}) => {
  try {
    const queryParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        queryParams.append(key, value)
      }
    })
    const response = await api.get(`/technical/${timeframe}?${queryParams.toString()}`)
    console.log('Technical data raw response:', response)
    console.log('Technical data response data:', response.data)
    console.log('Technical data response structure:', {
      hasSuccess: 'success' in response.data,
      hasData: 'data' in response.data,
      hasPagination: 'pagination' in response.data,
      hasMetadata: 'metadata' in response.data,
      dataLength: response.data.data?.length || 0
    })
    
    // The backend returns {success: true, data: [...], pagination: {...}, metadata: {...}}
    // We need to return the entire response structure, not just the data array
    return response.data
  } catch (error) {
    console.error('Error in getTechnicalData:', error)
    const errorMessage = handleApiError(error, 'get technical data')
    return { 
      success: false,
      data: [], 
      error: errorMessage,
      pagination: { page: 1, limit: 25, total: 0, totalPages: 0, hasNext: false, hasPrev: false },
      metadata: { timeframe, timestamp: new Date().toISOString() }
    }
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
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get eps revisions')
    return normalizeApiResponse({ data: [], error: errorMessage })
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
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get eps trend')
    return normalizeApiResponse({ data: [], error: errorMessage })
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
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get growth estimates')
    return normalizeApiResponse({ data: [], error: errorMessage })
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
    return normalizeApiResponse(response, true) // Array of NAAIM data
  } catch (error) {
    const errorMessage = handleApiError(error, 'get NAAIM data')
    return normalizeApiResponse({ error: errorMessage }, true)
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
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get economic data')
    return normalizeApiResponse({ data: [], error: errorMessage })
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
    return normalizeApiResponse(response, true) // Array of fear/greed data
  } catch (error) {
    const errorMessage = handleApiError(error, 'get fear & greed data')
    return normalizeApiResponse({ error: errorMessage }, true)
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
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get technical summary')
    return normalizeApiResponse({ data: [], error: errorMessage })
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
    const response = await api.get(`/calendar/earnings-metrics?${queryParams.toString()}`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get earnings metrics')
    return normalizeApiResponse({ data: [], error: errorMessage })
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

// Health check (robust: tries /health, then /)
export const healthCheck = async (queryParams = '') => {
  let triedRoot = false;
  let healthUrl = `/health${queryParams}`;
  let rootUrl = `/${queryParams}`;
  try {
    const response = await api.get(healthUrl, {
      baseURL: currentConfig.baseURL
    });
    console.log('Health check response:', response.data);
    return {
      data: response.data,
      healthy: true,
      endpoint: healthUrl,
      fallback: false,
      timestamp: new Date().toISOString()
    };
  } catch (error) {
    // If 404 or network error, try root endpoint
    console.warn('Health check failed for /health, trying root / endpoint...');
    triedRoot = true;
    try {
      const response = await api.get(rootUrl, {
        baseURL: currentConfig.baseURL
      });
      console.log('Root endpoint health check response:', response.data);
      return {
        data: response.data,
        healthy: true,
        endpoint: rootUrl,
        fallback: true,
        timestamp: new Date().toISOString()
      };
    } catch (rootError) {
      console.error('Error in health check (both endpoints failed):', rootError);
      const errorMessage = handleApiError(rootError, 'health check (both endpoints)');
      return {
        data: null,
        error: errorMessage,
        healthy: false,
        endpoint: triedRoot ? rootUrl : healthUrl,
        fallback: triedRoot,
        timestamp: new Date().toISOString()
      };
    }
  }
}

// Data validation functions
export const getDataValidationSummary = async () => {
  try {
    const response = await api.get('/api/health/full');
    return normalizeApiResponse(response, false);
  } catch (error) {
    console.error('Error fetching data validation summary:', error);
    throw error;
  }
};

// Get comprehensive stock price history - BULLETPROOF VERSION
export const getStockPriceHistory = async (ticker, limit = 90) => {
  try {
    console.log(`BULLETPROOF: Fetching price history for ${ticker} with limit ${limit}`);
    const response = await api.get(`/stocks/price-history/${ticker}?limit=${limit}`)
    console.log(`BULLETPROOF: Price history response received for ${ticker}:`, response.data);
    return response.data
  } catch (error) {
    console.error('BULLETPROOF: Error fetching stock price history:', error)
    throw error
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
  getEarningsMetrics,
  testApiConnection,
  getDiagnosticInfo,
  getApiConfig,
  getCurrentBaseURL,
  updateApiBaseUrl,
  getDatabaseHealthFull,
  getStockPriceHistory
}

