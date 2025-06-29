import axios from 'axios' 

// Get API configuration - exported for ServiceHealth
export const getApiConfig = () => {
  // Dynamic API URL resolution: runtime > build-time > fallback
  let runtimeApiUrl = (typeof window !== 'undefined' && window.__CONFIG__ && window.__CONFIG__.API_URL) ? window.__CONFIG__.API_URL : null;
  const apiUrl = runtimeApiUrl || import.meta.env.VITE_API_URL || 'http://localhost:3001';
  
  console.log('🔧 [API CONFIG] URL Resolution:', {
    runtimeApiUrl,
    envApiUrl: import.meta.env.VITE_API_URL,
    finalApiUrl: apiUrl,
    windowConfig: typeof window !== 'undefined' ? window.__CONFIG__ : 'undefined',
    allEnvVars: import.meta.env
  });
  
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

// Enhanced normalizeApiResponse function to handle all backend response formats
function normalizeApiResponse(response, expectArray = true) {
  console.log('🔍 normalizeApiResponse input:', {
    hasResponse: !!response,
    responseType: typeof response,
    hasData: !!(response && response.data !== undefined),
    dataType: response?.data ? typeof response.data : 'undefined',
    isArray: Array.isArray(response?.data),
    expectArray
  });
  
  // Handle axios response wrapper
  if (response && response.data !== undefined) {
    response = response.data;
  }
  
  // Handle backend API response format
  if (response && typeof response === 'object') {
    // If response has a 'data' property, use that
    if (response.data !== undefined) {
      response = response.data;
    }
    
    // If response has 'success' property, check if it's successful
    if (response.success === false) {
      console.error('❌ API request failed:', response.error);
      throw new Error(response.error || 'API request failed');
    }
    
    // If response has 'error' property, throw error
    if (response.error) {
      console.error('❌ API response contains error:', response.error);
      throw new Error(response.error);
    }
  }
  
  // Ensure we return an array if expected
  if (expectArray && !Array.isArray(response)) {
    if (response && typeof response === 'object') {
      // Try to extract array from common response structures
      if (Array.isArray(response.data)) {
        response = response.data;
      } else if (Array.isArray(response.items)) {
        response = response.items;
      } else if (Array.isArray(response.results)) {
        response = response.results;
      } else {
        // Convert object to array if it has numeric keys
        const keys = Object.keys(response);
        if (keys.length > 0 && keys.every(key => !isNaN(key))) {
          response = Object.values(response);
        } else {
          // Single item, wrap in array
          response = [response];
        }
      }
    } else {
      response = [];
    }
  }
  
  console.log('✅ normalizeApiResponse output:', {
    resultType: typeof response,
    isArray: Array.isArray(response),
    length: Array.isArray(response) ? response.length : 'N/A',
    sample: Array.isArray(response) && response.length > 0 ? response[0] : response
  });
  return response;
}

// --- PATCH: Log API config at startup ---
console.log('🚀 [API STARTUP] Initializing API configuration...');
console.log('🔧 [API CONFIG]', getApiConfig());
console.log('📡 [AXIOS DEFAULT BASE URL]', api.defaults.baseURL);

// Test connection on startup
setTimeout(async () => {
  try {
    console.log('🔍 [API STARTUP] Testing connection...');
    const testResponse = await api.get('/health', { timeout: 5000 });
    console.log('✅ [API STARTUP] Connection test successful:', testResponse.status);
  } catch (error) {
    console.warn('⚠️ [API STARTUP] Connection test failed:', error.message);
    console.log('🔧 [API STARTUP] Trying alternative health endpoints...');
    
    const altEndpoints = ['/api/health', '/api', '/'];
    for (const endpoint of altEndpoints) {
      try {
        const response = await api.get(endpoint, { timeout: 3000 });
        console.log(`✅ [API STARTUP] Alternative endpoint ${endpoint} successful:`, response.status);
        break;
      } catch (err) {
        console.log(`❌ [API STARTUP] Alternative endpoint ${endpoint} failed:`, err.message);
      }
    }
  }
}, 1000);

// --- PATCH: Wrap all API methods with normalizeApiResponse ---
// Market overview
export const getMarketOverview = async () => {
  console.log('📈 [API] Fetching market overview...');
  console.log('📈 [API] Current config:', getApiConfig());
  console.log('📈 [API] Axios baseURL:', api.defaults.baseURL);
  
  try {
    // Try multiple endpoint variations to catch URL issues
    const endpoints = ['/market/overview', '/api/market/overview'];
    let response = null;
    let lastError = null;
    
    for (const endpoint of endpoints) {
      try {
        console.log(`📈 [API] Trying endpoint: ${endpoint}`);
        response = await api.get(endpoint);
        console.log(`📈 [API] SUCCESS with endpoint: ${endpoint}`, response);
        break;
      } catch (err) {
        console.log(`📈 [API] FAILED endpoint: ${endpoint}`, err.message);
        lastError = err;
        continue;
      }
    }
    
    if (!response) {
      console.error('📈 [API] All endpoints failed, throwing last error:', lastError);
      throw lastError;
    }
    
    console.log('📈 [API] Market overview raw response:', response);
    const result = normalizeApiResponse(response, false);
    console.log('📈 [API] Market overview normalized result:', result);
    return result;
  } catch (error) {
    console.error('❌ [API] Market overview error details:', {
      message: error.message,
      status: error.response?.status,
      statusText: error.response?.statusText,
      data: error.response?.data,
      config: error.config,
      stack: error.stack
    });
    throw new Error(handleApiError(error, 'Failed to fetch market overview'));
  }
};

export const getMarketSentimentHistory = async (days = 30) => {
  console.log(`📊 [API] Fetching market sentiment history for ${days} days...`);
  
  try {
    // Try multiple endpoint variations
    const endpoints = [
      `/market/sentiment/history?days=${days}`,
      `/api/market/sentiment/history?days=${days}`
    ];
    
    let response = null;
    let lastError = null;
    
    for (const endpoint of endpoints) {
      try {
        console.log(`📊 [API] Trying sentiment endpoint: ${endpoint}`);
        response = await api.get(endpoint);
        console.log(`📊 [API] SUCCESS with sentiment endpoint: ${endpoint}`, response);
        break;
      } catch (err) {
        console.log(`📊 [API] FAILED sentiment endpoint: ${endpoint}`, err.message);
        lastError = err;
        continue;
      }
    }
    
    if (!response) {
      console.error('📊 [API] All sentiment endpoints failed:', lastError);
      throw lastError;
    }
    
    // The backend returns { data: [...], metadata: {...} }
    // We need to return this structure directly, not normalize it
    if (response.data && typeof response.data === 'object') {
      console.log('📊 [API] Returning sentiment data structure directly:', response.data);
      return response.data;
    }
    
    // Fallback to normalized response
    const result = normalizeApiResponse(response, true);
    console.log('📊 [API] Sentiment fallback normalized result:', result);
    return result;
  } catch (error) {
    console.error('❌ [API] Sentiment history error details:', {
      message: error.message,
      status: error.response?.status,
      data: error.response?.data
    });
    const errorMessage = handleApiError(error, 'get market sentiment history')
    return { error: errorMessage }
  }
}

export const getMarketSectorPerformance = async () => {
  console.log(`📊 [API] Fetching market sector performance...`);
  
  try {
    // Try multiple endpoint variations
    const endpoints = [
      `/market/sectors/performance`,
      `/api/market/sectors/performance`
    ];
    
    let response = null;
    let lastError = null;
    
    for (const endpoint of endpoints) {
      try {
        console.log(`📊 [API] Trying sector endpoint: ${endpoint}`);
        response = await api.get(endpoint);
        console.log(`📊 [API] SUCCESS with sector endpoint: ${endpoint}`, response);
        break;
      } catch (err) {
        console.log(`📊 [API] FAILED sector endpoint: ${endpoint}`, err.message);
        lastError = err;
        continue;
      }
    }
    
    if (!response) {
      console.error('📊 [API] All sector endpoints failed:', lastError);
      throw lastError;
    }
    
    // The backend returns { data: [...], metadata: {...} }
    // We need to return this structure directly, not normalize it
    if (response.data && typeof response.data === 'object') {
      console.log('📊 [API] Returning sector data structure directly:', response.data);
      return response.data;
    }
    
    // Fallback to normalized response
    const result = normalizeApiResponse(response, true);
    console.log('📊 [API] Sector fallback normalized result:', result);
    return result;
  } catch (error) {
    console.error('❌ [API] Sector performance error details:', {
      message: error.message,
      status: error.response?.status,
      data: error.response?.data
    });
    const errorMessage = handleApiError(error, 'get market sector performance')
    return { error: errorMessage }
  }
}

export const getMarketBreadth = async () => {
  console.log(`📊 [API] Fetching market breadth...`);
  
  try {
    // Try multiple endpoint variations
    const endpoints = [
      `/market/breadth`,
      `/api/market/breadth`
    ];
    
    let response = null;
    let lastError = null;
    
    for (const endpoint of endpoints) {
      try {
        console.log(`📊 [API] Trying breadth endpoint: ${endpoint}`);
        response = await api.get(endpoint);
        console.log(`📊 [API] SUCCESS with breadth endpoint: ${endpoint}`, response);
        break;
      } catch (err) {
        console.log(`📊 [API] FAILED breadth endpoint: ${endpoint}`, err.message);
        lastError = err;
        continue;
      }
    }
    
    if (!response) {
      console.error('📊 [API] All breadth endpoints failed:', lastError);
      throw lastError;
    }
    
    // The backend returns { data: {...}, metadata: {...} }
    // We need to return this structure directly, not normalize it
    if (response.data && typeof response.data === 'object') {
      console.log('📊 [API] Returning breadth data structure directly:', response.data);
      return response.data;
    }
    
    // Fallback to normalized response
    const result = normalizeApiResponse(response, false);
    console.log('📊 [API] Breadth fallback normalized result:', result);
    return result;
  } catch (error) {
    console.error('❌ [API] Market breadth error details:', {
      message: error.message,
      status: error.response?.status,
      data: error.response?.data
    });
    const errorMessage = handleApiError(error, 'get market breadth')
    return { error: errorMessage }
  }
}

export const getEconomicIndicators = async (days = 90) => {
  console.log(`📊 [API] Fetching economic indicators for ${days} days...`);
  
  try {
    // Try multiple endpoint variations
    const endpoints = [
      `/market/economic?days=${days}`,
      `/api/market/economic?days=${days}`
    ];
    
    let response = null;
    let lastError = null;
    
    for (const endpoint of endpoints) {
      try {
        console.log(`📊 [API] Trying economic endpoint: ${endpoint}`);
        response = await api.get(endpoint);
        console.log(`📊 [API] SUCCESS with economic endpoint: ${endpoint}`, response);
        break;
      } catch (err) {
        console.log(`📊 [API] FAILED economic endpoint: ${endpoint}`, err.message);
        lastError = err;
        continue;
      }
    }
    
    if (!response) {
      console.error('📊 [API] All economic endpoints failed:', lastError);
      throw lastError;
    }
    
    // The backend returns { data: [...], period_days: number, total_data_points: number }
    // We need to return this structure directly, not normalize it
    if (response.data && typeof response.data === 'object') {
      console.log('📊 [API] Returning economic data structure directly:', response.data);
      return response.data;
    }
    
    // Fallback to normalized response
    const result = normalizeApiResponse(response, true);
    console.log('📊 [API] Economic fallback normalized result:', result);
    return result;
  } catch (error) {
    console.error('❌ [API] Economic indicators error details:', {
      message: error.message,
      status: error.response?.status,
      data: error.response?.data
    });
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
  console.log('🚀 getStocks: Starting API call with params:', params);
  console.log('🚀 getStocks: Current config:', getApiConfig());
  
  try {
    const queryParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        queryParams.append(key, value)
      }
    })
    
    // Try multiple endpoint variations
    const endpoints = [
      `/stocks?${queryParams.toString()}`,
      `/api/stocks?${queryParams.toString()}`
    ];
    
    let response = null;
    let lastError = null;
    
    for (const endpoint of endpoints) {
      try {
        console.log(`� getStocks: Trying endpoint: ${endpoint}`);
        response = await api.get(endpoint, {
          baseURL: currentConfig.baseURL
        });
        console.log(`🚀 getStocks: SUCCESS with endpoint: ${endpoint}`, response);
        break;
      } catch (err) {
        console.log(`🚀 getStocks: FAILED endpoint: ${endpoint}`, err.message);
        lastError = err;
        continue;
      }
    }
    
    if (!response) {
      console.error('🚀 getStocks: All endpoints failed:', lastError);
      throw lastError;
    }
    
    console.log('📊 getStocks: Raw response:', {
      status: response.status,
      hasData: !!response.data,
      dataType: typeof response.data,
      dataKeys: response.data ? Object.keys(response.data) : []
    });
    
    // The backend returns { data: [...], pagination: {...}, metadata: {...} }
    // We need to return this structure directly, not normalize it
    if (response.data && typeof response.data === 'object') {
      console.log('✅ getStocks: returning backend response structure:', response.data);
      return response.data;
    }
    
    // Fallback to normalized response
    const normalized = normalizeApiResponse(response, true);
    console.log('🔄 getStocks: using normalized response:', normalized);
    return normalized;
  } catch (error) {
    console.error('❌ getStocks error details:', {
      message: error.message,
      status: error.response?.status,
      statusText: error.response?.statusText,
      data: error.response?.data,
      config: error.config
    });
    const errorMessage = handleApiError(error, 'get stocks')
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
  console.log('🚀 getStock: Starting API call for ticker:', ticker);
  try {
    const response = await api.get(`/api/stocks/${ticker}`)
    
    console.log('📊 getStock: Raw response:', {
      status: response.status,
      hasData: !!response.data,
      dataType: typeof response.data,
      dataKeys: response.data ? Object.keys(response.data) : []
    });
    
    const result = normalizeApiResponse(response, false) // Single stock is an object
    console.log('✅ getStock: returning result:', result);
    return result;
  } catch (error) {
    console.error('❌ Error fetching stock:', error)
    const errorMessage = handleApiError(error, 'get stock')
    return normalizeApiResponse({ error: errorMessage }, false)
  }
}

// New methods for StockDetail page
export const getStockProfile = async (ticker) => {
  try {
    const response = await api.get(`/api/stocks/${ticker}/profile`)
    return normalizeApiResponse(response, false)
  } catch (error) {
    const errorMessage = handleApiError(error, 'get stock profile')
    return normalizeApiResponse({ error: errorMessage }, false)
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
  console.log('🚀 getStockFinancials: Starting API call for ticker:', ticker, 'type:', type);
  try {
    const response = await api.get(`/api/financials/${ticker}/${type}`)
    
    console.log('📊 getStockFinancials: Raw response:', {
      status: response.status,
      hasData: !!response.data,
      dataType: typeof response.data,
      dataKeys: response.data ? Object.keys(response.data) : []
    });
    
    const result = normalizeApiResponse(response)
    console.log('✅ getStockFinancials: returning result:', result);
    return result;
  } catch (error) {
    console.error('❌ Error fetching stock financials:', error)
    const errorMessage = handleApiError(error, 'get stock financials')
    return normalizeApiResponse({ data: [], error: errorMessage })
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
    const url = `/api/stocks/screen?${params.toString()}`
    const response = await api.get(url, {
      baseURL: currentConfig.baseURL
    })
    
    // The backend returns { data: [...], pagination: {...}, metadata: {...} }
    // We need to return this structure directly, not normalize it
    if (response.data && typeof response.data === 'object') {
      console.log('screenStocks: returning backend response structure:', response.data);
      return response.data;
    }
    
    // Fallback to normalized response
    return normalizeApiResponse(response, true);
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
  console.log(`📊 [API] Fetching technical data for timeframe: ${timeframe}`, params);
  
  try {
    const queryParams = new URLSearchParams();
    queryParams.append('timeframe', timeframe);
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        queryParams.append(key, value);
      }
    });
    
    // Try multiple endpoint variations
    const endpoints = [
      `/technical/${timeframe}?${queryParams.toString()}`,
      `/api/technical/${timeframe}?${queryParams.toString()}`,
      `/technical/data?${queryParams.toString()}`,
      `/api/technical/data?${queryParams.toString()}`
    ];
    
    let response = null;
    let lastError = null;
    
    for (const endpoint of endpoints) {
      try {
        console.log(`📊 [API] Trying technical endpoint: ${endpoint}`);
        response = await api.get(endpoint);
        console.log(`📊 [API] SUCCESS with technical endpoint: ${endpoint}`, response);
        break;
      } catch (err) {
        console.log(`📊 [API] FAILED technical endpoint: ${endpoint}`, err.message);
        lastError = err;
        continue;
      }
    }
    
    if (!response) {
      console.error('📊 [API] All technical endpoints failed:', lastError);
      throw lastError;
    }
    
    // Always return { data, pagination, metadata }
    if (response.data && typeof response.data === 'object') {
      const { data, pagination, metadata } = response.data;
      console.log('📊 [API] Technical data structure:', { data: Array.isArray(data), pagination, metadata });
      return {
        data: Array.isArray(data) ? data : [],
        pagination: pagination || {},
        metadata: metadata || {},
        ...response.data
      };
    }
    // Fallback
    console.log('📊 [API] Technical data fallback structure');
    return { data: [], pagination: {}, metadata: {} };
  } catch (error) {
    console.error('❌ [API] Technical data error details:', {
      message: error.message,
      status: error.response?.status,
      data: error.response?.data
    });
    const errorMessage = handleApiError(error, 'get technical data');
    return {
      data: [],
      pagination: {},
      metadata: {},
      error: errorMessage
    };
  }
};

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
    return normalizeApiResponse(response, true) // Expect array of price data
  } catch (error) {
    console.error('BULLETPROOF: Error fetching stock price history:', error)
    throw error
  }
}

export const getRecentAnalystActions = async (limit = 10) => {
  try {
    const response = await api.get(`/api/analysts/recent-actions?limit=${limit}`)
    return normalizeApiResponse(response, true) // Expect array of analyst actions
  } catch (error) {
    const errorMessage = handleApiError(error, 'get recent analyst actions')
    return { 
      data: [], 
      summary: { date: null, total_actions: 0, upgrades: 0, downgrades: 0 },
      error: errorMessage 
    }
  }
}

// Add missing dashboard endpoints that the frontend is trying to call
export const getDashboardUser = async () => {
  try {
    const response = await api.get('/api/dashboard/user');
    return normalizeApiResponse(response, false);
  } catch (error) {
    console.error('getDashboardUser error:', error);
    // Return mock data for now
    return {
      data: {
        name: 'Demo User',
        email: 'demo@example.com',
        role: 'user'
      }
    };
  }
};

export const getDashboardWatchlist = async () => {
  try {
    const response = await api.get('/api/dashboard/watchlist');
    return normalizeApiResponse(response);
  } catch (error) {
    console.error('getDashboardWatchlist error:', error);
    // Return mock data for now
    return {
      data: ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA']
    };
  }
};

export const getDashboardPortfolio = async () => {
  try {
    const response = await api.get('/api/dashboard/portfolio');
    return normalizeApiResponse(response, false);
  } catch (error) {
    console.error('getDashboardPortfolio error:', error);
    // Return mock data for now
    return {
      data: {
        positions: [
          { symbol: 'AAPL', shares: 100, avgPrice: 150, value: 15000, pnl: 0.05 },
          { symbol: 'MSFT', shares: 50, avgPrice: 300, value: 15000, pnl: 0.08 }
        ],
        value: 30000,
        pnl: { daily: 500, mtd: 2000, ytd: 5000 }
      }
    };
  }
};

export const getDashboardPortfolioMetrics = async () => {
  try {
    const response = await api.get('/api/dashboard/portfolio/metrics');
    return normalizeApiResponse(response, false);
  } catch (error) {
    console.error('getDashboardPortfolioMetrics error:', error);
    // Return mock data for now
    return {
      data: {
        sharpe: 1.2,
        beta: 0.95,
        maxDrawdown: 0.15,
        volatility: 0.18
      }
    };
  }
};

export const getDashboardHoldings = async () => {
  console.log('💼 [API] Fetching dashboard holdings...');
  try {
    const response = await api.get('/dashboard/holdings');
    console.log('💼 [API] Dashboard holdings response:', response);
    return normalizeApiResponse(response, true);
  } catch (error) {
    console.error('❌ [API] Dashboard holdings error:', error);
    throw new Error(handleApiError(error, 'Failed to fetch dashboard holdings'));
  }
};

export const getDashboardUserSettings = async () => {
  try {
    const response = await api.get('/api/dashboard/user/settings');
    return normalizeApiResponse(response, false);
  } catch (error) {
    console.error('getDashboardUserSettings error:', error);
    // Return mock data for now
    return {
      data: {
        theme: 'light',
        notifications: true,
        email: 'demo@example.com'
      }
    };
  }
};

export const getDashboardMarketSummary = async () => {
  try {
    const response = await api.get('/api/dashboard/market-summary');
    return normalizeApiResponse(response);
  } catch (error) {
    console.error('getDashboardMarketSummary error:', error);
    // Return mock data for now
    return {
      data: [
        { name: 'S&P 500', value: 4500, change: 0.5, pct: '+0.5%' },
        { name: 'NASDAQ', value: 14000, change: 0.8, pct: '+0.8%' },
        { name: 'DOW', value: 35000, change: -0.2, pct: '-0.2%' }
      ]
    };
  }
};

export const getDashboardEarningsCalendar = async (symbol) => {
  try {
    const response = await api.get(`/api/dashboard/earnings-calendar?symbol=${symbol}`);
    return normalizeApiResponse(response);
  } catch (error) {
    console.error('getDashboardEarningsCalendar error:', error);
    // Return mock data for now
    return {
      data: [
        { event: 'Earnings Release', date: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString() },
        { event: 'Analyst Day', date: new Date(Date.now() + 14 * 24 * 60 * 60 * 1000).toISOString() }
      ]
    };
  }
};

export const getDashboardAnalystInsights = async (symbol) => {
  try {
    const response = await api.get(`/api/dashboard/analyst-insights?symbol=${symbol}`);
    return normalizeApiResponse(response);
  } catch (error) {
    console.error('getDashboardAnalystInsights error:', error);
    // Return mock data for now
    return {
      data: [
        { action: 'Upgrade', rating: 'Buy', analyst: 'Goldman Sachs' },
        { action: 'Maintain', rating: 'Hold', analyst: 'Morgan Stanley' }
      ]
    };
  }
};

export const getDashboardFinancialHighlights = async (symbol) => {
  try {
    const response = await api.get(`/api/dashboard/financial-highlights?symbol=${symbol}`);
    return normalizeApiResponse(response);
  } catch (error) {
    console.error('getDashboardFinancialHighlights error:', error);
    // Return mock data for now
    return {
      data: [
        { metric: 'P/E Ratio', value: '25.5' },
        { metric: 'Market Cap', value: '$2.5T' },
        { metric: 'Revenue Growth', value: '+15%' }
      ]
    };
  }
};

export const getDashboardSymbols = async () => {
  try {
    const response = await api.get('/api/dashboard/symbols');
    return normalizeApiResponse(response);
  } catch (error) {
    console.error('getDashboardSymbols error:', error);
    // Return mock data for now
    return {
      data: ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'SPY', 'QQQ', 'AMZN', 'META', 'NFLX']
    };
  }
};

export const getDashboardTechnicalSignals = async () => {
  try {
    const response = await api.get('/api/technical/daily?limit=10');
    return normalizeApiResponse(response);
  } catch (error) {
    console.error('getDashboardTechnicalSignals error:', error);
    // Return mock data for now
    return {
      data: [
        { symbol: 'AAPL', rsi: 65, macd: 0.5, stochastic_k: 70, atr: 2.5, date: new Date().toISOString() },
        { symbol: 'MSFT', rsi: 45, macd: -0.2, stochastic_k: 55, atr: 3.1, date: new Date().toISOString() }
      ]
    };
  }
};

// Simple API test function
export const testApiEndpoints = async () => {
  const results = {};
  
  try {
    // Test basic health check
    const healthResponse = await api.get('/api/health');
    results.health = { success: true, data: healthResponse.data };
  } catch (error) {
    results.health = { success: false, error: error.message };
  }
  
  try {
    // Test stocks endpoint
    const stocksResponse = await api.get('/api/stocks?limit=5');
    results.stocks = { success: true, data: stocksResponse.data };
  } catch (error) {
    results.stocks = { success: false, error: error.message };
  }
  
  try {
    // Test technical data endpoint
    const technicalResponse = await api.get('/api/technical/daily?limit=5');
    results.technical = { success: true, data: technicalResponse.data };
  } catch (error) {
    results.technical = { success: false, error: error.message };
  }
  
  try {
    // Test market overview endpoint
    const marketResponse = await api.get('/api/market/overview');
    results.market = { success: true, data: marketResponse.data };
  } catch (error) {
    results.market = { success: false, error: error.message };
  }
  
  console.log('API Test Results:', results);
  return results;
};

// Market indices
export const getMarketIndices = async () => {
  console.log('🚀 getMarketIndices: Starting API call...');
  try {
    const response = await api.get('/api/market/indices');
    
    console.log('📊 getMarketIndices: Raw response:', {
      status: response.status,
      hasData: !!response.data,
      dataType: typeof response.data,
      dataKeys: response.data ? Object.keys(response.data) : []
    });
    
    const result = normalizeApiResponse(response, true);
    console.log('✅ getMarketIndices: returning result:', result);
    return result;
  } catch (error) {
    console.error('❌ Error fetching market indices:', error);
    const errorMessage = handleApiError(error, 'get market indices');
    return normalizeApiResponse({ error: errorMessage }, true);
  }
};

// Sector performance
export const getSectorPerformance = async () => {
  console.log('🚀 getSectorPerformance: Starting API call...');
  try {
    const response = await api.get('/api/market/sectors');
    
    console.log('📊 getSectorPerformance: Raw response:', {
      status: response.status,
      hasData: !!response.data,
      dataType: typeof response.data,
      dataKeys: response.data ? Object.keys(response.data) : []
    });
    
    const result = normalizeApiResponse(response, true);
    console.log('✅ getSectorPerformance: returning result:', result);
    return result;
  } catch (error) {
    console.error('❌ Error fetching sector performance:', error);
    const errorMessage = handleApiError(error, 'get sector performance');
    return normalizeApiResponse({ error: errorMessage }, true);
  }
};

// Market volatility
export const getMarketVolatility = async () => {
  console.log('🚀 getMarketVolatility: Starting API call...');
  try {
    const response = await api.get('/api/market/volatility');
    
    console.log('📊 getMarketVolatility: Raw response:', {
      status: response.status,
      hasData: !!response.data,
      dataType: typeof response.data,
      dataKeys: response.data ? Object.keys(response.data) : []
    });
    
    const result = normalizeApiResponse(response, true);
    console.log('✅ getMarketVolatility: returning result:', result);
    return result;
  } catch (error) {
    console.error('❌ Error fetching market volatility:', error);
    const errorMessage = handleApiError(error, 'get market volatility');
    return normalizeApiResponse({ error: errorMessage }, true);
  }
};

// Economic calendar
export const getEconomicCalendar = async () => {
  console.log('🚀 getEconomicCalendar: Starting API call...');
  try {
    const response = await api.get('/api/market/calendar');
    
    console.log('📊 getEconomicCalendar: Raw response:', {
      status: response.status,
      hasData: !!response.data,
      dataType: typeof response.data,
      dataKeys: response.data ? Object.keys(response.data) : []
    });
    
    const result = normalizeApiResponse(response, true);
    console.log('✅ getEconomicCalendar: returning result:', result);
    return result;
  } catch (error) {
    console.error('❌ Error fetching economic calendar:', error);
    const errorMessage = handleApiError(error, 'get economic calendar');
    return normalizeApiResponse({ error: errorMessage }, true);
  }
};

// Market cap categories
export const getMarketCapCategories = async () => {
  console.log('🚀 getMarketCapCategories: Starting API call...');
  try {
    const response = await api.get('/api/stocks/market-cap-categories');
    
    console.log('📊 getMarketCapCategories: Raw response:', {
      status: response.status,
      hasData: !!response.data,
      dataType: typeof response.data,
      dataKeys: response.data ? Object.keys(response.data) : []
    });
    
    const result = normalizeApiResponse(response, true);
    console.log('✅ getMarketCapCategories: returning result:', result);
    return result;
  } catch (error) {
    console.error('❌ Error fetching market cap categories:', error);
    const errorMessage = handleApiError(error, 'get market cap categories');
    return normalizeApiResponse({ error: errorMessage }, true);
  }
};

// Technical indicators
export const getTechnicalIndicators = async (symbol, timeframe, indicators) => {
  console.log('🚀 getTechnicalIndicators: Starting API call...', { symbol, timeframe, indicators });
  try {
    const response = await api.get(`/api/technical/indicators/${symbol}`, {
      params: { timeframe, indicators: indicators.join(',') }
    });
    
    console.log('📊 getTechnicalIndicators: Raw response:', {
      status: response.status,
      hasData: !!response.data,
      dataType: typeof response.data,
      dataKeys: response.data ? Object.keys(response.data) : []
    });
    
    const result = normalizeApiResponse(response, true);
    console.log('✅ getTechnicalIndicators: returning result:', result);
    return result;
  } catch (error) {
    console.error('❌ Error fetching technical indicators:', error);
    const errorMessage = handleApiError(error, 'get technical indicators');
    return normalizeApiResponse({ error: errorMessage }, true);
  }
};

// Volume data
export const getVolumeData = async (symbol, timeframe) => {
  console.log('🚀 getVolumeData: Starting API call...', { symbol, timeframe });
  try {
    const response = await api.get(`/api/stocks/${symbol}/volume`, {
      params: { timeframe }
    });
    
    console.log('📊 getVolumeData: Raw response:', {
      status: response.status,
      hasData: !!response.data,
      dataType: typeof response.data,
      dataKeys: response.data ? Object.keys(response.data) : []
    });
    
    const result = normalizeApiResponse(response, true);
    console.log('✅ getVolumeData: returning result:', result);
    return result;
  } catch (error) {
    console.error('❌ Error fetching volume data:', error);
    const errorMessage = handleApiError(error, 'get volume data');
    return normalizeApiResponse({ error: errorMessage }, true);
  }
};

// Support resistance levels
export const getSupportResistanceLevels = async (symbol) => {
  console.log('🚀 getSupportResistanceLevels: Starting API call...', { symbol });
  try {
    const response = await api.get(`/api/technical/support-resistance/${symbol}`);
    
    console.log('📊 getSupportResistanceLevels: Raw response:', {
      status: response.status,
      hasData: !!response.data,
      dataType: typeof response.data,
      dataKeys: response.data ? Object.keys(response.data) : []
    });
    
    const result = normalizeApiResponse(response, false);
    console.log('✅ getSupportResistanceLevels: returning result:', result);
    return result;
  } catch (error) {
    console.error('❌ Error fetching support resistance levels:', error);
    const errorMessage = handleApiError(error, 'get support resistance levels');
    return normalizeApiResponse({ error: errorMessage }, false);
  }
};

// --- DASHBOARD API FUNCTIONS ---
export const getDashboardSummary = async () => {
  console.log('📊 [API] Fetching dashboard summary...');
  try {
    const response = await api.get('/dashboard/summary');
    console.log('📊 [API] Dashboard summary response:', response);
    return normalizeApiResponse(response, false);
  } catch (error) {
    console.error('❌ [API] Dashboard summary error:', error);
    throw new Error(handleApiError(error, 'Failed to fetch dashboard summary'));
  }
};

export const getDashboardPerformance = async () => {
  console.log('📈 [API] Fetching dashboard performance...');
  try {
    const response = await api.get('/dashboard/performance');
    console.log('📈 [API] Dashboard performance response:', response);
    return normalizeApiResponse(response, true);
  } catch (error) {
    console.error('❌ [API] Dashboard performance error:', error);
    throw new Error(handleApiError(error, 'Failed to fetch dashboard performance'));
  }
};

export const getDashboardAlerts = async () => {
  console.log('🚨 [API] Fetching dashboard alerts...');
  try {
    const response = await api.get('/dashboard/alerts');
    console.log('🚨 [API] Dashboard alerts response:', response);
    return normalizeApiResponse(response, true);
  } catch (error) {
    console.error('❌ [API] Dashboard alerts error:', error);
    throw new Error(handleApiError(error, 'Failed to fetch dashboard alerts'));
  }
};

export const getDashboardDebug = async () => {
  console.log('🔧 [API] Fetching dashboard debug info...');
  try {
    const response = await api.get('/dashboard/debug');
    console.log('🔧 [API] Dashboard debug response:', response);
    return normalizeApiResponse(response, false);
  } catch (error) {
    console.error('❌ [API] Dashboard debug error:', error);
    throw new Error(handleApiError(error, 'Failed to fetch dashboard debug info'));
  }
};

// --- MARKET API FUNCTIONS ---
export const getMarketIndicators = async () => {
  console.log('📊 [API] Fetching market indicators...');
  try {
    const response = await api.get('/market/indicators');
    console.log('📊 [API] Market indicators response:', response);
    return normalizeApiResponse(response, false);
  } catch (error) {
    console.error('❌ [API] Market indicators error:', error);
    throw new Error(handleApiError(error, 'Failed to fetch market indicators'));
  }
};

export const getMarketSentiment = async () => {
  console.log('😊 [API] Fetching market sentiment...');
  try {
    const response = await api.get('/market/sentiment');
    console.log('😊 [API] Market sentiment response:', response);
    return normalizeApiResponse(response, false);
  } catch (error) {
    console.error('❌ [API] Market sentiment error:', error);
    throw new Error(handleApiError(error, 'Failed to fetch market sentiment'));
  }
};

// --- FINANCIAL DATA API FUNCTIONS ---
export const getFinancialData = async (symbol) => {
  console.log(`💰 [API] Fetching financial data for ${symbol}...`);
  try {
    const response = await api.get(`/financials/data/${symbol}`);
    console.log(`💰 [API] Financial data response for ${symbol}:`, response);
    return normalizeApiResponse(response, false);
  } catch (error) {
    console.error(`❌ [API] Financial data error for ${symbol}:`, error);
    throw new Error(handleApiError(error, `Failed to fetch financial data for ${symbol}`));
  }
};

export const getEarningsData = async (symbol) => {
  console.log(`📊 [API] Fetching earnings data for ${symbol}...`);
  try {
    const response = await api.get(`/financials/earnings/${symbol}`);
    console.log(`📊 [API] Earnings data response for ${symbol}:`, response);
    return normalizeApiResponse(response, true);
  } catch (error) {
    console.error(`❌ [API] Earnings data error for ${symbol}:`, error);
    throw new Error(handleApiError(error, `Failed to fetch earnings data for ${symbol}`));
  }
};

export const getCashFlow = async (symbol) => {
  console.log(`💵 [API] Fetching cash flow for ${symbol}...`);
  try {
    const response = await api.get(`/financials/cash-flow/${symbol}`);
    console.log(`💵 [API] Cash flow response for ${symbol}:`, response);
    return normalizeApiResponse(response, true);
  } catch (error) {
    console.error(`❌ [API] Cash flow error for ${symbol}:`, error);
    throw new Error(handleApiError(error, `Failed to fetch cash flow for ${symbol}`));
  }
};

// --- TECHNICAL ANALYSIS API FUNCTIONS ---
export const getTechnicalHistory = async (symbol) => {
  console.log(`📊 [API] Fetching technical history for ${symbol}...`);
  try {
    const response = await api.get(`/technical/history/${symbol}`);
    console.log(`📊 [API] Technical history response for ${symbol}:`, response);
    return normalizeApiResponse(response, true);
  } catch (error) {
    console.error(`❌ [API] Technical history error for ${symbol}:`, error);
    throw new Error(handleApiError(error, `Failed to fetch technical history for ${symbol}`));
  }
};

// --- STOCK API FUNCTIONS ---
export const getStockInfo = async (symbol) => {
  console.log(`ℹ️ [API] Fetching stock info for ${symbol}...`);
  try {
    const response = await api.get(`/stocks/info/${symbol}`);
    console.log(`ℹ️ [API] Stock info response for ${symbol}:`, response);
    return normalizeApiResponse(response, false);
  } catch (error) {
    console.error(`❌ [API] Stock info error for ${symbol}:`, error);
    throw new Error(handleApiError(error, `Failed to fetch stock info for ${symbol}`));
  }
};

export const getStockPrice = async (symbol) => {
  console.log(`💰 [API] Fetching stock price for ${symbol}...`);
  try {
    const response = await api.get(`/stocks/price/${symbol}`);
    console.log(`💰 [API] Stock price response for ${symbol}:`, response);
    return normalizeApiResponse(response, false);
  } catch (error) {
    console.error(`❌ [API] Stock price error for ${symbol}:`, error);
    throw new Error(handleApiError(error, `Failed to fetch stock price for ${symbol}`));
  }
};

export const getStockHistory = async (symbol) => {
  console.log(`📊 [API] Fetching stock history for ${symbol}...`);
  try {
    const response = await api.get(`/stocks/history/${symbol}`);
    console.log(`📊 [API] Stock history response for ${symbol}:`, response);
    return normalizeApiResponse(response, true);
  } catch (error) {
    console.error(`❌ [API] Stock history error for ${symbol}:`, error);
    throw new Error(handleApiError(error, `Failed to fetch stock history for ${symbol}`));
  }
};

export const searchStocks = async (query) => {
  console.log(`🔍 [API] Searching stocks with query: ${query}...`);
  try {
    const response = await api.get(`/stocks/search?q=${encodeURIComponent(query)}`);
    console.log(`🔍 [API] Stock search response:`, response);
    return normalizeApiResponse(response, true);
  } catch (error) {
    console.error(`❌ [API] Stock search error:`, error);
    throw new Error(handleApiError(error, 'Failed to search stocks'));
  }
};

// --- HEALTH CHECK ---
export const getHealth = async () => {
  console.log('🏥 [API] Checking API health...');
  try {
    const response = await api.get('/health');
    console.log('🏥 [API] Health check response:', response);
    return normalizeApiResponse(response, false);
  } catch (error) {
    console.error('❌ [API] Health check error:', error);
    throw new Error(handleApiError(error, 'Failed to check API health'));
  }
};

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
  getRecentAnalystActions,
  getDashboardUser,
  getDashboardWatchlist,
  getDashboardPortfolio,
  getDashboardPortfolioMetrics,
  getDashboardHoldings,
  getDashboardUserSettings,
  getDashboardMarketSummary,
  getDashboardEarningsCalendar,
  getDashboardAnalystInsights,
  getDashboardFinancialHighlights,
  getDashboardSymbols,
  getDashboardTechnicalSignals,
  testApiEndpoints,
  getMarketIndices,
  getSectorPerformance,
  getMarketVolatility,
  getEconomicCalendar,
  getMarketCapCategories,
  getTechnicalIndicators,
  getVolumeData,
  getSupportResistanceLevels,
  getDashboardSummary,
  getDashboardPerformance,
  getDashboardAlerts,
  getDashboardDebug
}

