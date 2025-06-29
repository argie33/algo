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
    await new Promise(resolve => setTimeout(resolve, delay))
    return api(requestConfig)
  }
  
  return Promise.reject(error)
}

// Request interceptor for logging and Lambda optimization
api.interceptors.request.use(
  (config) => {
    // Remove any double /api/api
    if (config.url && config.url.startsWith('/api/api')) {
      config.url = config.url.replace('/api/api', '/api');
    }
    
    const fullUrl = `${config.baseURL || api.defaults.baseURL}${config.url}`;
    console.log('[API REQUEST FINAL URL]', fullUrl, config);
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
    console.log('[API SUCCESS]', response.config.method?.toUpperCase(), fullUrl, response)
    return response
  },
  async (error) => {
    console.error('[API ERROR]', error)
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
  console.log('normalizeApiResponse input:', response);
  if (response && response.data) return response.data;
  return expectArray ? [] : {};
}

// --- PATCH: Log API config at startup ---
console.log('[API CONFIG]', getApiConfig());
console.log('[AXIOS DEFAULT BASE URL]', api.defaults.baseURL);

// --- PATCH: Wrap all API methods with normalizeApiResponse ---
// Market overview
export const getMarketOverview = async () => {
  try {
    const response = await api.get('/api/market/overview', {
      baseURL: currentConfig.baseURL
    })
    const normalized = normalizeApiResponse(response, false) // Market overview is an object
    return normalized
  } catch (error) {
    console.error('Error fetching market overview:', error)
    const errorMessage = handleApiError(error, 'market overview')
    return { error: errorMessage }
  }
}

export const getMarketSentimentHistory = async (days = 30) => {
  try {
    const response = await api.get(`/api/market/sentiment/history?days=${days}`)
    return normalizeApiResponse(response, true) // Array of historical data
  } catch (error) {
    const errorMessage = handleApiError(error, 'get market sentiment history')
    return { error: errorMessage }
  }
}

export const getMarketSectorPerformance = async () => {
  try {
    const response = await api.get('/api/market/sectors/performance')
    return normalizeApiResponse(response, true) // Array of sector data
  } catch (error) {
    const errorMessage = handleApiError(error, 'get market sector performance')
    return { error: errorMessage }
  }
}

export const getMarketBreadth = async () => {
  try {
    const response = await api.get('/api/market/breadth')
    return normalizeApiResponse(response, false) // Market breadth is an object
  } catch (error) {
    const errorMessage = handleApiError(error, 'get market breadth')
    return { error: errorMessage }
  }
}

export const getEconomicIndicators = async (days = 90) => {
  try {
    const response = await api.get(`/api/market/economic?days=${days}`)
    return response.data
  } catch (error) {
    const errorMessage = handleApiError(error, 'get economic indicators')
    console.error('Error fetching economic indicators:', error)
    return { 
      data: [], 
      error: errorMessage,
      period_days: days,
      total_data_points: 0,
      timestamp: new Date().toISOString()
    }
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
    const url = `/api/stocks?${queryParams.toString()}`
    const response = await api.get(url, {
      baseURL: currentConfig.baseURL
    });
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
    const response = await api.get(`/api/stocks/quick/overview?${queryParams.toString()}`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get stocks quick')
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

// Chunked stocks loading
export const getStocksChunk = async (chunkIndex = 0) => {
  try {
    const response = await api.get(`/api/stocks/chunk/${chunkIndex}`)
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
    const response = await api.get(`/api/stocks/full/data?${queryParams.toString()}`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get stocks full')
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

export const getStock = async (ticker) => {
  try {
    const response = await api.get(`/api/stocks/${ticker}`)
    return normalizeApiResponse(response, false) // Single stock is an object
  } catch (error) {
    const errorMessage = handleApiError(error, 'get stock')
    return normalizeApiResponse({ error: errorMessage }, false)
  }
}

// New methods for StockDetail page
export const getStockProfile = async (ticker) => {
  try {
    const response = await api.get(`/api/stocks/${ticker}/profile`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get stock profile')
    return normalizeApiResponse({ data: null, error: errorMessage })
  }
}

export const getStockMetrics = async (ticker) => {
  try {
    const response = await api.get(`/api/stocks/${ticker}/metrics`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get stock metrics')
    return normalizeApiResponse({ data: null, error: errorMessage })
  }
}

export const getStockFinancials = async (ticker, type = 'income') => {
  try {
    const response = await api.get(`/api/stocks/${ticker}/financials?type=${type}`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get stock financials')
    return normalizeApiResponse({ data: null, error: errorMessage })
  }
}

export const getAnalystRecommendations = async (ticker) => {
  try {
    const response = await api.get(`/api/stocks/${ticker}/recommendations`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get analyst recommendations')
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

export const getStockPrices = async (ticker, timeframe = 'daily', limit = 100) => {
  try {
    const response = await api.get(`/api/stocks/${ticker}/prices?timeframe=${timeframe}&limit=${limit}`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get stock prices')
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

export const getStockPricesRecent = async (ticker, limit = 30) => {
  try {
    const response = await api.get(`/api/stocks/${ticker}/price-recent?limit=${limit}`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get stock prices recent')
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

export const getStockRecommendations = async (ticker) => {
  try {
    const response = await api.get(`/api/stocks/${ticker}/recommendations`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get stock recommendations')
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

export const getSectors = async () => {
  try {
    const response = await api.get('/api/stocks/filters/sectors')
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
    const response = await api.get(`/api/metrics/valuation?${queryParams.toString()}`)
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
    const response = await api.get(`/api/metrics/growth?${queryParams.toString()}`)
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
    const response = await api.get(`/api/metrics/dividends?${queryParams.toString()}`)
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
    const response = await api.get(`/api/metrics/financial-strength?${queryParams.toString()}`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get financial strength metrics')
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

// New method for stock screening with proper parameter handling
export const screenStocks = async (params) => {
  try {
    const url = `/api/stocks?${params.toString()}`
    const response = await api.get(url, {
      baseURL: currentConfig.baseURL
    })
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
    const response = await api.get('/api/signals/buy', {
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
    const response = await api.get('/api/signals/sell', {
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
    const response = await api.get(`/api/calendar/earnings-estimates?${queryParams.toString()}`, {
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
    const response = await api.get(`/api/calendar/earnings-history?${queryParams.toString()}`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get earnings history')
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

// Ticker-based endpoints (wrap Axios promise for consistency)
export const getTickerEarningsEstimates = async (ticker) => {
  try {
    const response = await api.get(`/api/analysts/${ticker}/earnings-estimates`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get ticker earnings estimates')
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

export const getTickerEarningsHistory = async (ticker) => {
  try {
    const response = await api.get(`/api/analysts/${ticker}/earnings-history`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get ticker earnings history')
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

export const getTickerRevenueEstimates = async (ticker) => {
  try {
    const response = await api.get(`/api/analysts/${ticker}/revenue-estimates`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get ticker revenue estimates')
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

export const getTickerEpsRevisions = async (ticker) => {
  try {
    const response = await api.get(`/api/analysts/${ticker}/eps-revisions`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get ticker eps revisions')
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

export const getTickerEpsTrend = async (ticker) => {
  try {
    const response = await api.get(`/api/analysts/${ticker}/eps-trend`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get ticker eps trend')
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

export const getTickerGrowthEstimates = async (ticker) => {
  try {
    const response = await api.get(`/api/analysts/${ticker}/growth-estimates`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get ticker growth estimates')
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

export const getTickerAnalystRecommendations = async (ticker) => {
  try {
    const response = await api.get(`/api/analysts/${ticker}/recommendations`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get ticker analyst recommendations')
    return normalizeApiResponse({ data: [], error: errorMessage })
  }
}

export const getAnalystOverview = async (ticker) => {
  try {
    const response = await api.get(`/api/analysts/${ticker}/overview`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get analyst overview')
    return normalizeApiResponse({ data: null, error: errorMessage })
  }
}

// Financial statements endpoint (wrap for consistency)
export const getFinancialStatements = async (ticker, period = 'annual') => {
  try {
    const response = await api.get(`/api/financials/${ticker}/financials?period=${period}`)
    return normalizeApiResponse(response)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get financial statements')
    return normalizeApiResponse({ data: null, error: errorMessage })
  }
}

export const getIncomeStatement = async (ticker, period = 'annual') => {
  try {
    const url = `/api/financials/${ticker}/income-statement?period=${period}`
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
    const url = `/api/financials/${ticker}/cash-flow?period=${period}`
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
    const url = `/api/financials/${ticker}/balance-sheet?period=${period}`
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
    const url = `/api/financials/${ticker}/key-metrics`
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
    const response = await api.get(`/api/financials/all?${queryParams.toString()}`)
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
    const response = await api.get(`/api/financials/metrics?${queryParams.toString()}`)
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
    const response = await api.get(`/api/technical/${timeframe}?${queryParams.toString()}`)
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
    const response = await api.get(`/api/eps/revisions?${queryParams.toString()}`)
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
    const response = await api.get(`/api/eps/trend?${queryParams.toString()}`)
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
    const response = await api.get(`/api/growth/estimates?${queryParams.toString()}`)
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
    const response = await api.get(`/api/market/naaim?${queryParams.toString()}`)
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
    const response = await api.get(`/api/economic/data?${queryParams.toString()}`)
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
    const response = await api.get(`/api/market/fear-greed?${queryParams.toString()}`)
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
    const response = await api.get(`/api/technical/summary?${queryParams.toString()}`)
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
    const response = await api.get(`/api/calendar/earnings-metrics?${queryParams.toString()}`)
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
    const response = await api.get('/api/health?quick=true', {
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
        fullUrl: (customUrl || currentConfig.baseURL) + '/api/health?quick=true'
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
    const response = await api.get('/api/health/database', {
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
  let healthUrl = `/api/health${queryParams}`;
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
    console.warn('Health check failed for /api/health, trying root / endpoint...');
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
    const response = await api.get(`/api/stocks/price-history/${ticker}?limit=${limit}`)
    console.log(`BULLETPROOF: Price history response received for ${ticker}:`, response.data);
    return response.data
  } catch (error) {
    console.error('BULLETPROOF: Error fetching stock price history:', error)
    throw error
  }
}

export const getRecentAnalystActions = async (limit = 10) => {
  try {
    const response = await api.get(`/api/analysts/recent-actions?limit=${limit}`)
    return response.data
  } catch (error) {
    const errorMessage = handleApiError(error, 'get recent analyst actions')
    return { 
      data: [], 
      summary: { date: null, total_actions: 0, upgrades: 0, downgrades: 0 },
      error: errorMessage 
    }
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
  getStockPriceHistory,
  getRecentAnalystActions
}

