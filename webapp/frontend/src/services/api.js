import axios from "axios";

// Get API configuration - exported for ServiceHealth
export const getApiConfig = () => {
  // Dynamic API URL resolution: runtime > build-time > fallback
  let runtimeApiUrl =
    typeof window !== "undefined" &&
    window.__CONFIG__ &&
    window.__CONFIG__.API_URL
      ? window.__CONFIG__.API_URL
      : null;
  const apiUrl =
    runtimeApiUrl || import.meta.env.VITE_API_URL || "http://localhost:3001";

  console.log("🔧 [API CONFIG] URL Resolution:", {
    runtimeApiUrl,
    envApiUrl: import.meta.env.VITE_API_URL,
    finalApiUrl: apiUrl,
    windowConfig:
      typeof window !== "undefined" ? window.__CONFIG__ : "undefined",
    allEnvVars: import.meta.env,
  });

  return {
    baseURL: apiUrl,
    isServerless: !!apiUrl && !apiUrl.includes("localhost"),
    apiUrl: apiUrl,
    isConfigured: !!apiUrl && !apiUrl.includes("localhost"),
    environment: import.meta.env.MODE,
    isDevelopment: import.meta.env.DEV,
    isProduction: import.meta.env.PROD,
    baseUrl: import.meta.env.BASE_URL,
    allEnvVars: import.meta.env,
  };
};

// Create API instance that can be updated
let currentConfig = getApiConfig();

// API health check state
let apiHealthy = true;
let lastHealthCheck = 0;
const HEALTH_CHECK_INTERVAL = 30000; // 30 seconds

// Simple health check function
const _checkApiHealth = async () => {
  const now = Date.now();
  if (now - lastHealthCheck < HEALTH_CHECK_INTERVAL) {
    return apiHealthy;
  }
  
  try {
    const response = await fetch(`${currentConfig.baseURL}/health`, { 
      method: 'GET',
      timeout: 3000,
      signal: AbortSignal.timeout(3000)
    });
    apiHealthy = response.ok;
    lastHealthCheck = now;
  } catch (error) {
    apiHealthy = false;
    lastHealthCheck = now;
  }
  
  return apiHealthy;
};

// Warn if API URL is fallback (localhost)
if (!currentConfig.apiUrl || currentConfig.apiUrl.includes("localhost")) {
  console.warn(
    "[API CONFIG] Using fallback API URL:",
    currentConfig.baseURL +
      "\nSet window.__CONFIG__.API_URL at runtime or VITE_API_URL at build time to override."
  );
}

const api = axios.create({
  baseURL: currentConfig.baseURL,
  timeout: currentConfig.isServerless ? 45000 : 30000, // Longer timeout for Lambda cold starts
  headers: {
    "Content-Type": "application/json",
  },
});

// Export the api instance for direct use
export { api };

// Portfolio API functions
export const getPortfolioData = async () => {
  try {
    const response = await api.get("/api/portfolio/holdings");
    return response?.data || null;
  } catch (error) {
    console.error("Error fetching portfolio data:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw error;
  }
};

export const addHolding = async (holding) => {
  try {
    const response = await api.post("/api/portfolio/holdings", holding);
    return response?.data;
  } catch (error) {
    console.error("Error adding holding:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw error;
  }
};

export const updateHolding = async (holdingId, holding) => {
  try {
    const response = await api.put(
      `/api/portfolio/holdings/${holdingId}`,
      holding
    );
    return response?.data;
  } catch (error) {
    console.error("Error updating holding:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw error;
  }
};

export const deleteHolding = async (holdingId) => {
  try {
    const response = await api.delete(`/api/portfolio/holdings/${holdingId}`);
    return response?.data;
  } catch (error) {
    console.error("Error deleting holding:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw error;
  }
};

export const importPortfolioFromBroker = async (broker) => {
  try {
    const response = await api.post(`/api/portfolio/import/${broker}`);
    return response?.data;
  } catch (error) {
    console.error("Error importing portfolio from broker:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw error;
  }
};

export const getPortfolioPerformance = async (timeframe = "1Y") => {
  try {
    const response = await api.get(
      `/api/portfolio/performance?timeframe=${timeframe}`
    );
    return response?.data;
  } catch (error) {
    console.error("Error fetching portfolio performance:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw error;
  }
};

export const getBenchmarkData = async (timeframe = "1Y") => {
  try {
    const response = await api.get(
      `/api/portfolio/benchmark?timeframe=${timeframe}`
    );
    return response?.data;
  } catch (error) {
    console.error("Error fetching benchmark data:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw error;
  }
};

export const getPortfolioOptimizationData = async () => {
  try {
    const response = await api.get("/api/portfolio/optimization");
    return response?.data;
  } catch (error) {
    console.error("Error fetching optimization data:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw error;
  }
};

export const runPortfolioOptimization = async (params) => {
  try {
    const response = await api.post("/api/portfolio/optimization/run", params);
    return response?.data;
  } catch (error) {
    console.error("Error running portfolio optimization:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw error;
  }
};

export const getRebalancingRecommendations = async () => {
  try {
    const response = await api.get("/api/portfolio/rebalance");
    return response?.data;
  } catch (error) {
    console.error("Error fetching rebalancing recommendations:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw error;
  }
};

export const getRiskAnalysis = async () => {
  try {
    const response = await api.get("/api/portfolio/risk");
    return response?.data;
  } catch (error) {
    console.error("Error fetching risk analysis:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw error;
  }
};

// API Keys management
export const getApiKeys = async () => {
  try {
    const response = await api.get("/api/settings/api-keys");
    return response?.data;
  } catch (error) {
    console.error("Error fetching API keys:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw error;
  }
};

export const addApiKey = async (apiKeyData) => {
  try {
    const response = await api.post("/api/settings/api-keys", apiKeyData);
    return response?.data;
  } catch (error) {
    console.error("Error adding API key:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw error;
  }
};

export const updateApiKey = async (keyId, apiKeyData) => {
  try {
    const response = await api.put(
      `/api/settings/api-keys/${keyId}`,
      apiKeyData
    );
    return response?.data;
  } catch (error) {
    console.error("Error updating API key:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw error;
  }
};

export const deleteApiKey = async (keyId) => {
  try {
    const response = await api.delete(`/api/settings/api-keys/${keyId}`);
    return response?.data;
  } catch (error) {
    console.error("Error deleting API key:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw error;
  }
};

// Function to get current base URL
export const getCurrentBaseURL = () => {
  return currentConfig.baseURL;
};

// Function to update API base URL dynamically
export const updateApiBaseUrl = (newUrl) => {
  currentConfig = { ...currentConfig, baseURL: newUrl, apiUrl: newUrl };
  api.defaults.baseURL = newUrl;
};

// Retry configuration for Lambda cold starts
const _retryHandler = async (error) => {
  const { config: requestConfig } = error;

  if (!requestConfig || requestConfig.retryCount >= 3) {
    return Promise.reject(error);
  }

  requestConfig.retryCount = requestConfig.retryCount || 0;
  requestConfig.retryCount += 1;
  // Only retry on timeout or 5xx errors (common with Lambda cold starts)
  if (
    error.code === "ECONNABORTED" ||
    (error.response && error.response.status >= 500)
  ) {
    const delay = Math.pow(2, requestConfig.retryCount) * 1000; // Exponential backoff
    await new Promise((resolve) => setTimeout(resolve, delay));
    return api(requestConfig);
  }

  return Promise.reject(error);
};

// Request interceptor for logging and Lambda optimization
api.interceptors.request.use(
  (config) => {
    // DEVELOPMENT MODE: Only block API calls if no API server is configured
    const isDevelopment = window.location.hostname === 'localhost' || 
                         window.location.hostname === '127.0.0.1' ||
                         window.location.port === '5173';
    
    // Only block API calls in development if we don't have a configured API server
    const hasValidApiServer = currentConfig && currentConfig.baseURL && 
                              (currentConfig.baseURL.startsWith('http://localhost:') || 
                               currentConfig.baseURL.startsWith('https://'));
    
    if (isDevelopment && !hasValidApiServer) {
      console.log('🚫 [API] Blocking API call - no server configured:', {
        baseURL: currentConfig.baseURL,
        hasValidApiServer
      });
      const error = new Error('API calls disabled - no server configured');
      error.code = 'NO_SERVER_CONFIGURED';
      return Promise.reject(error);
    }
    
    console.log('✅ [API] Allowing API call:', {
      isDevelopment,
      hasValidApiServer,
      baseURL: currentConfig.baseURL,
      url: config.url
    });
    // Remove any double /api/api
    if (config.url && config.url.startsWith("/api/api")) {
      config.url = config.url.replace("/api/api", "/api");
    }

    // Add authentication token if available
    try {
      // Try to get auth token from localStorage or sessionStorage
      let authToken = null;

      // Check if we're in browser context
      if (typeof window !== "undefined") {
        // Try various storage locations for auth token
        authToken =
          localStorage.getItem("authToken") ||
          sessionStorage.getItem("authToken") ||
          localStorage.getItem("accessToken") ||
          sessionStorage.getItem("accessToken");
      }

      // Development mode: Use dev-bypass-token for localhost or when dev auth is forced
      if (import.meta.env.DEV && (
        currentConfig.baseURL.includes('localhost:3001') || 
        import.meta.env.VITE_FORCE_DEV_AUTH === 'true'
      )) {
        // If we have a dev token from devAuth service, replace it with bypass token
        if (!authToken || (authToken && authToken.startsWith('dev-'))) {
          console.log("🔧 Development mode: Using dev-bypass-token for API calls");
          authToken = "dev-bypass-token";
        }
      }

      if (authToken) {
        config.headers["Authorization"] = `Bearer ${authToken}`;
      }
    } catch (error) {
      console.log("Could not retrieve auth token:", error.message);
    }

    const fullUrl = `${config.baseURL || api.defaults.baseURL}${config.url}`;
    console.log("[API REQUEST FINAL URL]", fullUrl, config);
    if (config.isServerless) {
      config.headers["X-Lambda-Request"] = "true";
      config.headers["X-Request-Time"] = new Date().toISOString();
    }
    return config;
  },
  (error) => {
    console.error("API Request Error:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    return Promise.reject(error);
  }
);

// Enhanced diagnostics: Use our robust error logging system
api.interceptors.response.use(
  (response) => {
    const fullUrl = `${response.config.baseURL || api.defaults.baseURL}${response.config.url}`;
    console.log(
      "[API SUCCESS]",
      response.config.method?.toUpperCase(),
      fullUrl,
      {
        status: response.status,
        statusText: response.statusText,
        dataSize: response?.data ? (Array.isArray(response?.data) ? (response.data?.length || 0) : Object.keys(response?.data).length) : 0
      }
    );
    return response;
  },
  async (error) => {
    // Suppress all error logging in development mode to avoid console spam
    // Components should handle API errors gracefully with fallback data
    
    // Especially suppress development mode blocked requests
    if (error?.code === 'DEV_MODE_BLOCKED') {
      return Promise.reject(error);
    }
    
    return Promise.reject(error);
  }
);

// --- Add this utility for consistent error handling ---
function handleApiError(error, context = "") {
  let message = "An unexpected error occurred";
  if (error?.response?.data?.error) {
    message = error.response?.data.error;
  } else if (error?.response?.data?.message) {
    message = error.response?.data.message;
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
  console.log("🔍 normalizeApiResponse input:", {
    hasResponse: !!response,
    responseType: typeof response,
    hasData: !!(response && response?.data !== undefined),
    dataType: response?.data ? typeof response?.data : "undefined",
    isArray: Array.isArray(response?.data),
    expectArray,
  });

  // Handle axios response wrapper
  if (response && response?.data !== undefined) {
    response = response?.data;
  }

  // Handle backend API response format
  if (response && typeof response === "object") {
    // If response has a 'data' property, use that
    if (response?.data !== undefined) {
      response = response?.data;
    }

    // If response has 'success' property, check if it's successful
    if (response.success === false) {
      console.error("❌ API request failed:", response.error);
      throw new Error(response.error || "API request failed");
    }

    // If response has 'error' property, throw error
    if (response.error) {
      console.error("❌ API response contains error:", response.error);
      throw new Error(response.error);
    }
  }

  // Ensure we return an array if expected
  if (expectArray && !Array.isArray(response)) {
    if (response && typeof response === "object") {
      // Try to extract array from common response structures
      if (Array.isArray(response?.data)) {
        response = response?.data;
      } else if (Array.isArray(response.items)) {
        response = response.items;
      } else if (Array.isArray(response.results)) {
        response = response.results;
      } else {
        // Convert object to array if it has numeric keys
        const keys = Object.keys(response);
        if (keys.length > 0 && keys.every((key) => !isNaN(key))) {
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

  console.log("✅ normalizeApiResponse output:", {
    resultType: typeof response,
    isArray: Array.isArray(response),
    length: Array.isArray(response) ? (response?.length || 0) : "N/A",
    sample:
      Array.isArray(response) && response.length > 0 ? response[0] : response,
  });
  return response;
}

// --- PATCH: Log API config at startup ---
console.log("🚀 [API STARTUP] Initializing API configuration...");
console.log("🔧 [API CONFIG]", getApiConfig());
console.log("📡 [AXIOS DEFAULT BASE URL]", api.defaults.baseURL);

// DISABLED: Test connection on startup (was causing maximum call stack exceeded)
// setTimeout(async () => {
//   try {
//     console.log("🔍 [API STARTUP] Testing connection...");
//     const testResponse = await api.get("/health", { timeout: 5000 });
//     console.log(
//       "✅ [API STARTUP] Connection test successful:",
//       testResponse.status
//     );
//   } catch (error) {
//     console.warn("⚠️ [API STARTUP] Connection test failed:", error.message);
//   }
// }, 1000);

// --- PATCH: Wrap all API methods with normalizeApiResponse ---
// Market overview
export const getMarketOverview = async () => {
  console.log("📈 [API] Fetching market overview...");
  console.log("📈 [API] Current config:", getApiConfig());
  console.log("📈 [API] Axios baseURL:", api.defaults.baseURL);

  try {
    // Use the correct endpoint for our API  
    const endpoints = ["/api/dashboard/summary"];
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
      // Use console.warn for expected backend offline errors
      const isExpectedError = lastError?.message === 'Network Error' || lastError?.code === 'ERR_NETWORK' || lastError?.response?.status === 503;
      if (isExpectedError) {
        console.warn("⚠️ [API] Market overview endpoints unavailable:", lastError?.message || 'Unknown error');
      } else {
        console.error("📈 [API] All market overview endpoints failed:", lastError);
      }
      throw lastError;
    }

    console.log("📈 [API] Market overview raw response:", response);
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, false);
    console.log("📈 [API] Market overview normalized result:", result);
    return { data: result };
  } catch (error) {
    // Use console.warn for expected errors (503 = backend offline), console.error for unexpected
    const isExpectedError = error.response?.status === 503 || error.response?.status === 502 || error.message === 'Network Error' || error.code === 'ERR_NETWORK';
    const logLevel = isExpectedError ? 'warn' : 'error';
    const logPrefix = isExpectedError ? '⚠️ [API] Market overview unavailable' : '❌ [API] Market overview error';
    
    console[logLevel](`${logPrefix}:`, error?.message || 'Unknown error');
    
    // Only log full details for unexpected errors
    if (!isExpectedError) {
      console.error("Full error details:", {
        status: error.response?.status,
        statusText: error.response?.statusText,
        url: error.config?.url,
        method: error.config?.method
      });
    }
    
    throw new Error(handleApiError(error, "Failed to fetch market overview"));
  }
};

export const getTopStocks = async (params = {}) => {
  console.log("📈 [API] Fetching top stocks...", params);
  console.log("📈 [API] Current config:", getApiConfig());
  
  try {
    const queryParams = new URLSearchParams({
      limit: params.limit || 10,
      sortBy: params.sortBy || 'composite_score',
      sortOrder: params.sortOrder || 'desc',
      ...params
    }).toString();
    
    // Use the correct endpoint for our API
    const endpoints = [`/api/scores?${queryParams}`];
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
      // Use console.warn for expected backend offline errors
      const isExpectedError = lastError?.message === 'Network Error' || lastError?.code === 'ERR_NETWORK' || lastError?.response?.status === 503;
      if (isExpectedError) {
        console.warn("⚠️ [API] Top stocks endpoints unavailable:", lastError?.message || 'Unknown error');
      } else {
        console.error("📈 [API] All top stocks endpoints failed:", lastError);
      }
      throw lastError;
    }

    console.log("📈 [API] Top stocks raw response:", response);
    const result = normalizeApiResponse(response, false);
    console.log("📈 [API] Top stocks normalized result:", result);
    return { data: result };
  } catch (error) {
    // Use console.warn for expected errors (503 = backend offline), console.error for unexpected
    const isExpectedError = error.response?.status === 503 || error.response?.status === 502 || error.message === 'Network Error' || error.code === 'ERR_NETWORK';
    const logLevel = isExpectedError ? 'warn' : 'error';
    const logPrefix = isExpectedError ? '⚠️ [API] Top stocks unavailable' : '❌ [API] Top stocks error';
    
    console[logLevel](`${logPrefix}:`, error?.message || 'Unknown error');
    
    // Only log full details for unexpected errors
    if (!isExpectedError) {
      console.error("Full error details:", {
        status: error.response?.status,
        statusText: error.response?.statusText,
        url: error.config?.url,
        method: error.config?.method
      });
    }
    throw new Error(handleApiError(error, "Failed to fetch top stocks"));
  }
};

export const getMarketSentimentHistory = async (days = 30) => {
  console.log(`📊 [API] Fetching market sentiment history for ${days} days...`);

  try {
    // Try multiple endpoint variations
    // Use the correct endpoint for Lambda (without /api prefix)
    const endpoints = [
      `/market/sentiment/history?days=${days}`,
      `/api/market/sentiment/history?days=${days}`,
    ];

    let response = null;
    let lastError = null;

    for (const endpoint of endpoints) {
      try {
        console.log(`📊 [API] Trying sentiment endpoint: ${endpoint}`);
        response = await api.get(endpoint);
        console.log(
          `📊 [API] SUCCESS with sentiment endpoint: ${endpoint}`,
          response
        );
        break;
      } catch (err) {
        console.log(
          `📊 [API] FAILED sentiment endpoint: ${endpoint}`,
          err.message
        );
        lastError = err;
        continue;
      }
    }

    if (!response) {
      console.error("📊 [API] All sentiment endpoints failed:", {
        message: lastError?.message || 'Unknown error',
        status: lastError.response?.status,
        url: lastError.config?.url
      });
      throw lastError;
    }

    // Always return { data: ... } structure for consistency
    if (response?.data && typeof response?.data === "object") {
      console.log(
        "📊 [API] Returning sentiment data structure:",
        response?.data
      );
      return response?.data; // Backend already returns { data: ..., metadata: ... }
    }

    // Fallback to normalized response
    const result = normalizeApiResponse(response, true);
    console.log("📊 [API] Sentiment fallback normalized result:", result);
    return { data: result };
  } catch (error) {
    console.error("❌ [API] Sentiment history error details:", {
      message: error.message,
      status: error.response?.status,
      url: error.config?.url,
      method: error.config?.method,
    });
    const errorMessage = handleApiError(error, "get market sentiment history");
    return { data: [], error: errorMessage };
  }
};

export const getMarketSectorPerformance = async () => {
  console.log(`📊 [API] Fetching market sector performance...`);

  try {
    // Try multiple endpoint variations
    // Use the correct endpoint for Lambda (without /api prefix)
    const endpoints = [
      `/market/sectors/performance`,
      `/api/market/sectors/performance`,
    ];

    let response = null;
    let lastError = null;

    for (const endpoint of endpoints) {
      try {
        console.log(`📊 [API] Trying sector endpoint: ${endpoint}`);
        response = await api.get(endpoint);
        console.log(
          `📊 [API] SUCCESS with sector endpoint: ${endpoint}`,
          response
        );
        break;
      } catch (err) {
        console.log(
          `📊 [API] FAILED sector endpoint: ${endpoint}`,
          err.message
        );
        lastError = err;
        continue;
      }
    }

    if (!response) {
      console.error("📊 [API] All sector endpoints failed:", {
        message: lastError?.message || 'Unknown error',
        status: lastError.response?.status,
        url: lastError.config?.url
      });
      throw lastError;
    }

    // Always return { data: ... } structure for consistency
    if (response?.data && typeof response?.data === "object") {
      console.log("📊 [API] Returning sector data structure:", response?.data);
      return response?.data; // Backend already returns { data: ..., metadata: ... }
    }

    // Fallback to normalized response
    const result = normalizeApiResponse(response, true);
    console.log("📊 [API] Sector fallback normalized result:", result);
    return { data: result };
  } catch (error) {
    console.error("❌ [API] Sector performance error details:", {
      message: error.message,
      status: error.response?.status,
      url: error.config?.url,
      method: error.config?.method,
    });
    const errorMessage = handleApiError(error, "get market sector performance");
    return { data: [], error: errorMessage };
  }
};

export const getMarketBreadth = async () => {
  console.log(`📊 [API] Fetching market breadth...`);

  try {
    // Try multiple endpoint variations
    // Use the correct endpoint for Lambda (without /api prefix)
    const endpoints = [`/market/breadth`, `/api/market/breadth`];

    let response = null;
    let lastError = null;

    for (const endpoint of endpoints) {
      try {
        console.log(`📊 [API] Trying breadth endpoint: ${endpoint}`);
        response = await api.get(endpoint);
        console.log(
          `📊 [API] SUCCESS with breadth endpoint: ${endpoint}`,
          response
        );
        break;
      } catch (err) {
        console.log(
          `📊 [API] FAILED breadth endpoint: ${endpoint}`,
          err.message
        );
        lastError = err;
        continue;
      }
    }

    if (!response) {
      console.error("📊 [API] All breadth endpoints failed:", {
        message: lastError?.message || 'Unknown error',
        status: lastError.response?.status,
        url: lastError.config?.url
      });
      throw lastError;
    }

    // Always return { data: ... } structure for consistency
    if (response?.data && typeof response?.data === "object") {
      console.log("📊 [API] Returning breadth data structure:", response?.data);
      return response?.data; // Backend already returns { data: ..., metadata: ... }
    }

    // Fallback to normalized response
    const result = normalizeApiResponse(response, false);
    console.log("📊 [API] Breadth fallback normalized result:", result);
    return { data: result };
  } catch (error) {
    console.error("❌ [API] Market breadth error details:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText,
      url: error.config?.url,
      method: error.config?.method,
    });
    const errorMessage = handleApiError(error, "get market breadth");
    return { data: {}, error: errorMessage };
  }
};

export const getEconomicIndicators = async (days = 90) => {
  console.log(`📊 [API] Fetching economic indicators for ${days} days...`);

  try {
    // Try multiple endpoint variations
    // Use the correct endpoint for Lambda (without /api prefix)
    const endpoints = [
      `/market/economic?days=${days}`,
      `/api/market/economic?days=${days}`,
    ];

    let response = null;
    let lastError = null;

    for (const endpoint of endpoints) {
      try {
        console.log(`📊 [API] Trying economic endpoint: ${endpoint}`);
        response = await api.get(endpoint);
        console.log(
          `📊 [API] SUCCESS with economic endpoint: ${endpoint}`,
          response
        );
        break;
      } catch (err) {
        console.log(
          `📊 [API] FAILED economic endpoint: ${endpoint}`,
          err.message
        );
        lastError = err;
        continue;
      }
    }

    if (!response) {
      console.error("📊 [API] All economic endpoints failed:", {
        message: lastError?.message || 'Unknown error',
        status: lastError.response?.status,
        url: lastError.config?.url
      });
      throw lastError;
    }

    // Always return { data: ... } structure for consistency
    if (response?.data && typeof response?.data === "object") {
      console.log("📊 [API] Returning economic data structure:", response?.data);
      return response?.data; // Backend already returns { data: ..., period_days: ..., total_data_points: ... }
    }

    // Fallback to normalized response
    const result = normalizeApiResponse(response, true);
    console.log("📊 [API] Economic fallback normalized result:", result);
    return { data: result };
  } catch (error) {
    console.error("❌ [API] Economic indicators error details:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText,
      url: error.config?.url,
      method: error.config?.method,
    });
    const errorMessage = handleApiError(error, "get economic indicators");
    return {
      data: [],
      error: errorMessage,
      period_days: days,
      total_data_points: 0,
      timestamp: new Date().toISOString(),
    };
  }
};

export const getSeasonalityData = async () => {
  console.log("📅 [API] Fetching seasonality data...");

  try {
    // Try multiple endpoint variations
    const endpoints = ["/api/market/seasonality"];

    let response = null;
    let lastError = null;

    for (const endpoint of endpoints) {
      try {
        console.log(`📅 [API] Trying seasonality endpoint: ${endpoint}`);
        response = await api.get(endpoint);
        console.log(
          `📅 [API] SUCCESS with seasonality endpoint: ${endpoint}`,
          response
        );
        break;
      } catch (err) {
        console.log(
          `📅 [API] FAILED seasonality endpoint: ${endpoint}`,
          err.message
        );
        lastError = err;
        continue;
      }
    }

    if (!response) {
      console.error("📅 [API] All seasonality endpoints failed:", {
        message: lastError?.message || 'Unknown error',
        status: lastError.response?.status,
        url: lastError.config?.url
      });
      throw lastError;
    }

    // Always return { data: ... } structure for consistency
    if (response?.data && typeof response?.data === "object") {
      console.log(
        "📅 [API] Returning seasonality data structure:",
        response?.data
      );
      return response?.data; // Backend already returns { data: ..., success: ... }
    }

    // Fallback to normalized response
    const result = normalizeApiResponse(response, true);
    console.log("📅 [API] Seasonality fallback normalized result:", result);
    return { data: result };
  } catch (error) {
    console.error("❌ [API] Seasonality error details:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText,
      url: error.config?.url,
      method: error.config?.method,
    });
    const errorMessage = handleApiError(error, "get seasonality data");
    return {
      data: null,
      error: errorMessage,
      timestamp: new Date().toISOString(),
    };
  }
};

export const getMarketResearchIndicators = async () => {
  console.log("🔬 [API] Fetching market research indicators...");

  try {
    // Use the correct endpoint for our API
    const endpoints = [
      "/api/market/research-indicators",
    ];

    let response = null;
    let lastError = null;

    for (const endpoint of endpoints) {
      try {
        console.log(
          `🔬 [API] Trying research indicators endpoint: ${endpoint}`
        );
        response = await api.get(endpoint);
        console.log(
          `🔬 [API] SUCCESS with research indicators endpoint: ${endpoint}`,
          response
        );
        break;
      } catch (err) {
        console.log(
          `🔬 [API] FAILED research indicators endpoint: ${endpoint}`,
          err.message
        );
        lastError = err;
        continue;
      }
    }

    if (!response) {
      console.error(
        "🔬 [API] All research indicators endpoints failed:",
        lastError
      );
      throw lastError;
    }

    // Always return { data: ... } structure for consistency
    if (response?.data && typeof response?.data === "object") {
      console.log(
        "🔬 [API] Returning research indicators data structure:",
        response?.data
      );
      return response?.data; // Backend already returns { data: ..., success: ... }
    }

    // Fallback to normalized response
    const result = normalizeApiResponse(response, true);
    console.log(
      "🔬 [API] Research indicators fallback normalized result:",
      result
    );
    return { data: result };
  } catch (error) {
    console.error("❌ [API] Research indicators error details:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText,
      url: error.config?.url,
      method: error.config?.method,
    });
    const errorMessage = handleApiError(
      error,
      "get market research indicators"
    );
    return {
      data: null,
      error: errorMessage,
      timestamp: new Date().toISOString(),
    };
  }
};

export const getPortfolioAnalytics = async (timeframe = "1y") => {
  console.log("📈 [API] Fetching portfolio analytics...");

  try {
    const endpoints = [
      `/api/portfolio/analytics?timeframe=${timeframe}`,
    ];

    let response = null;
    let lastError = null;

    for (const endpoint of endpoints) {
      try {
        console.log(
          `📈 [API] Trying portfolio analytics endpoint: ${endpoint}`
        );
        response = await api.get(endpoint);
        console.log(
          `📈 [API] SUCCESS with portfolio analytics endpoint: ${endpoint}`,
          response
        );
        break;
      } catch (err) {
        console.log(
          `📈 [API] FAILED portfolio analytics endpoint: ${endpoint}`,
          err.message
        );
        lastError = err;
        continue;
      }
    }

    if (!response) {
      console.error(
        "📈 [API] All portfolio analytics endpoints failed:",
        lastError
      );
      throw lastError;
    }

    return response?.data;
  } catch (error) {
    console.error("❌ [API] Portfolio analytics error details:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText,
      url: error.config?.url,
      method: error.config?.method,
      stack: error?.stack?.substring(0, 500) + "..."
    });
    const errorMessage = handleApiError(error, "get portfolio analytics");
    return {
      data: null,
      error: errorMessage,
      timestamp: new Date().toISOString(),
    };
  }
};

export const getPortfolioRiskAnalysis = async () => {
  console.log("⚠️ [API] Fetching portfolio risk analysis...");

  try {
    const endpoints = [
      `/api/portfolio/risk-analysis`,
    ];

    let response = null;
    let lastError = null;

    for (const endpoint of endpoints) {
      try {
        console.log(
          `⚠️ [API] Trying portfolio risk analysis endpoint: ${endpoint}`
        );
        response = await api.get(endpoint);
        console.log(
          `⚠️ [API] SUCCESS with portfolio risk analysis endpoint: ${endpoint}`,
          response
        );
        break;
      } catch (err) {
        console.log(
          `⚠️ [API] FAILED portfolio risk analysis endpoint: ${endpoint}`,
          err.message
        );
        lastError = err;
        continue;
      }
    }

    if (!response) {
      console.error(
        "⚠️ [API] All portfolio risk analysis endpoints failed:",
        lastError
      );
      throw lastError;
    }

    return response?.data;
  } catch (error) {
    console.error("❌ [API] Portfolio risk analysis error details:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText,
      url: error.config?.url,
      method: error.config?.method,
      stack: error?.stack?.substring(0, 500) + "..."
    });
    const errorMessage = handleApiError(error, "get portfolio risk analysis");
    return {
      data: null,
      error: errorMessage,
      timestamp: new Date().toISOString(),
    };
  }
};

export const getPortfolioOptimization = async () => {
  console.log("🎯 [API] Fetching portfolio optimization...");

  try {
    const endpoints = [
      `/api/portfolio/optimization`,
    ];

    let response = null;
    let lastError = null;

    for (const endpoint of endpoints) {
      try {
        console.log(
          `🎯 [API] Trying portfolio optimization endpoint: ${endpoint}`
        );
        response = await api.get(endpoint);
        console.log(
          `🎯 [API] SUCCESS with portfolio optimization endpoint: ${endpoint}`,
          response
        );
        break;
      } catch (err) {
        console.log(
          `🎯 [API] FAILED portfolio optimization endpoint: ${endpoint}`,
          err.message
        );
        lastError = err;
        continue;
      }
    }

    if (!response) {
      console.error(
        "🎯 [API] All portfolio optimization endpoints failed:",
        lastError
      );
      throw lastError;
    }

    return response?.data;
  } catch (error) {
    console.error("❌ [API] Portfolio optimization error details:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText,
      url: error.config?.url,
      method: error.config?.method,
      stack: error?.stack?.substring(0, 500) + "..."
    });
    const errorMessage = handleApiError(error, "get portfolio optimization");
    return {
      data: null,
      error: errorMessage,
      timestamp: new Date().toISOString(),
    };
  }
};

// Stocks - Updated to use optimized endpoints
export const getStocks = async (params = {}) => {
  console.log("🚀 getStocks: Starting API call with params:", params);

  try {
    const queryParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        queryParams.append(key, value);
      }
    });

    // Use the correct endpoint for our API
    const endpoints = [
      `/api/stocks?${queryParams.toString()}`,
    ];

    let response = null;
    let lastError = null;

    for (const endpoint of endpoints) {
      try {
        console.log(`🚀 getStocks: Trying endpoint: ${endpoint}`);
        response = await api.get(endpoint, {
          baseURL: currentConfig.baseURL,
        });
        console.log(
          `🚀 getStocks: SUCCESS with endpoint: ${endpoint}`,
          response
        );
        break;
      } catch (err) {
        console.log(`🚀 getStocks: FAILED endpoint: ${endpoint}`, err.message);
        lastError = err;
        continue;
      }
    }

    if (!response) {
      console.error("🚀 getStocks: All endpoints failed:", lastError);
      throw lastError;
    }

    console.log("📊 getStocks: Raw response:", {
      status: response.status,
      hasData: !!response?.data,
      dataType: typeof response?.data,
      dataKeys: response?.data ? Object.keys(response?.data) : [],
    });

    // Handle backend response structure: { data: [...], total: ..., pagination: {...} }
    if (response?.data && Array.isArray(response?.data.data)) {
      console.log(
        "✅ getStocks: returning backend response structure:",
        response?.data
      );
      return response?.data; // Return the full backend response structure
    }

    // Fallback to normalized response
    const result = normalizeApiResponse(response, true);
    console.log("✅ getStocks: returning normalized result:", result);
    return { data: result };
  } catch (error) {
    console.error("❌ Error fetching stocks:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText,
      url: error.config?.url,
      method: error.config?.method,
      stack: error?.stack?.substring(0, 500) + "..."
    });
    const errorMessage = handleApiError(error, "get stocks");
    return { data: [], error: errorMessage };
  }
};

// Quick stocks overview for initial page load
export const getStocksQuick = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        queryParams.append(key, value);
      }
    });
    const response = await api.get(
      `/api/stocks/quick/overview?${queryParams.toString()}`
    );
    return normalizeApiResponse(response);
  } catch (error) {
    const errorMessage = handleApiError(error, "get stocks quick");
    return normalizeApiResponse({ data: [], error: errorMessage });
  }
};

// Chunked stocks loading
export const getStocksChunk = async (chunkIndex = 0) => {
  try {
    const response = await api.get(`/api/stocks/chunk/${chunkIndex}`);
    return normalizeApiResponse(response);
  } catch (error) {
    const errorMessage = handleApiError(error, "get stocks chunk");
    return normalizeApiResponse({ data: [], error: errorMessage });
  }
};

// Full stocks data (use with caution)
export const getStocksFull = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams();
    // Force small limit for safety
    if (!params.limit || params.limit > 10) {
      params.limit = 5;
      console.warn("Stocks limit reduced to 5 for performance");
    }
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        queryParams.append(key, value);
      }
    });
    const response = await api.get(
      `/api/stocks/full/data?${queryParams.toString()}`
    );
    return normalizeApiResponse(response);
  } catch (error) {
    const errorMessage = handleApiError(error, "get stocks full");
    return normalizeApiResponse({ data: [], error: errorMessage });
  }
};

export const getStock = async (ticker) => {
  console.log("🚀 getStock: Starting API call for ticker:", ticker);
  try {
    const response = await api.get(`/api/stocks/${ticker}`);

    console.log("📊 getStock: Raw response:", {
      status: response.status,
      hasData: !!response?.data,
      dataType: typeof response?.data,
      dataKeys: response?.data ? Object.keys(response?.data) : [],
    });

    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, false); // Single stock is an object
    console.log("✅ getStock: returning result:", result);
    return { data: result };
  } catch (error) {
    console.error("❌ Error fetching stock:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText,
      url: error.config?.url,
      method: error.config?.method,
      stack: error?.stack?.substring(0, 500) + "..."
    });
    const errorMessage = handleApiError(error, "get stock");
    return { data: null, error: errorMessage };
  }
};

// New methods for StockDetail page
export const getStockProfile = async (ticker) => {
  try {
    const response = await api.get(`/api/stocks/${ticker}/profile`);
    return normalizeApiResponse(response, false);
  } catch (error) {
    const errorMessage = handleApiError(error, "get stock profile");
    return normalizeApiResponse({ error: errorMessage }, false);
  }
};

export const getStockMetrics = async (ticker) => {
  try {
    const response = await api.get(`/api/metrics/${ticker}`);
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, false);
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(error, "get stock metrics");
    return { data: null, error: errorMessage };
  }
};

export const getStockFinancials = async (ticker, type = "income") => {
  console.log(
    "🚀 getStockFinancials: Starting API call for ticker:",
    ticker,
    "type:",
    type
  );
  try {
    const response = await api.get(`/api/financials/${ticker}/${type}`);

    console.log("📊 getStockFinancials: Raw response:", {
      status: response.status,
      hasData: !!response?.data,
      dataType: typeof response?.data,
      dataKeys: response?.data ? Object.keys(response?.data) : [],
    });

    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    console.log("✅ getStockFinancials: returning result:", result);
    return { data: result };
  } catch (error) {
    console.error("❌ Error fetching stock financials:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText,
      url: error.config?.url,
      method: error.config?.method,
      stack: error?.stack?.substring(0, 500) + "..."
    });
    const errorMessage = handleApiError(error, "get stock financials");
    return { data: [], error: errorMessage };
  }
};

export const getAnalystRecommendations = async (ticker) => {
  try {
    const response = await api.get(`/api/analysts/${ticker}/recommendations`);
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(error, "get analyst recommendations");
    return { data: [], error: errorMessage };
  }
};

export const getStockPrices = async (
  ticker,
  timeframe = "daily",
  limit = 100
) => {
  try {
    const response = await api.get(
      `/api/stocks/${ticker}/prices?timeframe=${timeframe}&limit=${limit}`
    );
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(error, "get stock prices");
    return { data: [], error: errorMessage };
  }
};

export const getStockPricesRecent = async (ticker, limit = 30) => {
  try {
    const response = await api.get(
      `/api/stocks/${ticker}/prices/recent?limit=${limit}`
    );
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(error, "get recent stock prices");
    return { data: [], error: errorMessage };
  }
};

export const getStockRecommendations = async (ticker) => {
  try {
    const response = await api.get(`/api/stocks/${ticker}/recommendations`);
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(error, "get stock recommendations");
    return { data: [], error: errorMessage };
  }
};

export const getSectors = async () => {
  try {
    const response = await api.get("/api/stocks/filters/sectors");
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(error, "get sectors");
    return { data: [], error: errorMessage };
  }
};

export const getValuationMetrics = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        queryParams.append(key, value);
      }
    });
    const response = await api.get(
      `/api/metrics/valuation?${queryParams.toString()}`
    );
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(error, "get valuation metrics");
    return { data: [], error: errorMessage };
  }
};

export const getGrowthMetrics = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        queryParams.append(key, value);
      }
    });
    const response = await api.get(
      `/api/metrics/growth?${queryParams.toString()}`
    );
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(error, "get growth metrics");
    return { data: [], error: errorMessage };
  }
};

export const getDividendMetrics = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        queryParams.append(key, value);
      }
    });
    const response = await api.get(
      `/api/metrics/dividends?${queryParams.toString()}`
    );
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(error, "get dividend metrics");
    return { data: [], error: errorMessage };
  }
};

export const getFinancialStrengthMetrics = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        queryParams.append(key, value);
      }
    });
    const response = await api.get(
      `/api/metrics/financial-strength?${queryParams.toString()}`
    );
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(
      error,
      "get financial strength metrics"
    );
    return { data: [], error: errorMessage };
  }
};

// New method for stock screening with proper parameter handling
export const screenStocks = async (params) => {
  try {
    // Use the main stocks endpoint since /screen endpoint has routing issues
    // The main endpoint supports filtering and pagination just like screening
    const endpoint = "/api/stocks";

    console.log("🔍 [API] Screening stocks with params:", params.toString());
    console.log(
      `🔍 [API] Using main stocks endpoint: ${endpoint}?${params.toString()}`
    );

    const response = await api.get(`${endpoint}?${params.toString()}`, {
      baseURL: currentConfig.baseURL,
    });

    console.log(`✅ [API] Success with main stocks endpoint:`, response?.data);

    // Backend returns: { success: true, data: [...], total: ..., pagination: {...} }
    if (
      response?.data &&
      response?.data.success &&
      Array.isArray(response?.data.data)
    ) {
      console.log("✅ [API] Using backend response structure:", response?.data);
      return response?.data;
    }

    // Fallback to normalized response
    const result = normalizeApiResponse(response, true);
    console.log("✅ [API] Using normalized response:", result);
    return {
      success: true,
      data: result,
      total: (result?.length || 0),
      pagination: {
        total: (result?.length || 0),
        page: 1,
        limit: (result?.length || 0),
      },
    };
  } catch (error) {
    console.error("❌ [API] Error screening stocks:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    const errorMessage = handleApiError(error, "screen stocks");
    return {
      success: false,
      data: [],
      error: errorMessage,
      total: 0,
      pagination: {
        total: 0,
        page: 1,
        limit: 25,
      },
    };
  }
};

// Trading signals endpoints
export const getBuySignals = async () => {
  console.log("📈 [API] Fetching buy signals...");
  try {
    // Mock data for now since backend endpoint might not exist
    const mockBuySignals = [
      {
        symbol: "AAPL",
        signal: "Buy",
        date: "2024-01-20",
        price: 150.25,
        changePercent: 2.15,
        strength: "Strong",
      },
      {
        symbol: "MSFT",
        signal: "Buy",
        date: "2024-01-19",
        price: 320.5,
        changePercent: 1.75,
        strength: "Medium",
      },
      {
        symbol: "TSLA",
        signal: "Buy",
        date: "2024-01-17",
        price: 850.75,
        changePercent: 3.25,
        strength: "Strong",
      },
      {
        symbol: "NVDA",
        signal: "Buy",
        date: "2024-01-16",
        price: 450.25,
        changePercent: 4.1,
        strength: "Strong",
      },
      {
        symbol: "AMZN",
        signal: "Buy",
        date: "2024-01-15",
        price: 155.8,
        changePercent: 1.85,
        strength: "Medium",
      },
    ];
    console.log("📈 [API] Returning mock buy signals:", mockBuySignals);
    return { data: mockBuySignals };
  } catch (error) {
    console.error("❌ [API] Buy signals error:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw new Error(handleApiError(error, "Failed to fetch buy signals"));
  }
};

export const getSellSignals = async () => {
  console.log("📉 [API] Fetching sell signals...");
  try {
    // Mock data for now since backend endpoint might not exist
    const mockSellSignals = [
      {
        symbol: "GOOGL",
        signal: "Sell",
        date: "2024-01-18",
        price: 2750.0,
        changePercent: -0.85,
        strength: "Medium",
      },
      {
        symbol: "META",
        signal: "Sell",
        date: "2024-01-17",
        price: 380.25,
        changePercent: -1.2,
        strength: "Weak",
      },
      {
        symbol: "NFLX",
        signal: "Sell",
        date: "2024-01-16",
        price: 485.5,
        changePercent: -0.95,
        strength: "Medium",
      },
    ];
    console.log("📉 [API] Returning mock sell signals:", mockSellSignals);
    return { data: mockSellSignals };
  } catch (error) {
    console.error("❌ [API] Sell signals error:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw new Error(handleApiError(error, "Failed to fetch sell signals"));
  }
};

// Earnings and analyst endpoints
export const getEarningsEstimates = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        queryParams.append(key, value);
      }
    });
    const response = await api.get(
      `/api/calendar/earnings-estimates?${queryParams.toString()}`,
      {
        baseURL: currentConfig.baseURL,
      }
    );
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(error, "get earnings estimates");
    return { data: [], error: errorMessage };
  }
};

export const getEarningsHistory = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        queryParams.append(key, value);
      }
    });
    const response = await api.get(
      `/api/calendar/earnings-history?${queryParams.toString()}`,
      {
        baseURL: currentConfig.baseURL,
      }
    );
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(error, "get earnings history");
    return { data: [], error: errorMessage };
  }
};

// Ticker-based endpoints (wrap Axios promise for consistency)
export const getTickerEarningsEstimates = async (ticker) => {
  try {
    const response = await api.get(
      `/api/analysts/${ticker}/earnings-estimates`
    );
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(error, "get ticker earnings estimates");
    return { data: [], error: errorMessage };
  }
};

export const getTickerEarningsHistory = async (ticker) => {
  try {
    const response = await api.get(`/api/analysts/${ticker}/earnings-history`);
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(error, "get ticker earnings history");
    return { data: [], error: errorMessage };
  }
};

export const getTickerRevenueEstimates = async (ticker) => {
  try {
    const response = await api.get(`/api/analysts/${ticker}/revenue-estimates`);
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(error, "get ticker revenue estimates");
    return { data: [], error: errorMessage };
  }
};

export const getTickerEpsRevisions = async (ticker) => {
  try {
    const response = await api.get(`/api/analysts/${ticker}/eps-revisions`);
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(error, "get ticker eps revisions");
    return { data: [], error: errorMessage };
  }
};

export const getTickerEpsTrend = async (ticker) => {
  try {
    const response = await api.get(`/api/analysts/${ticker}/eps-trend`);
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(error, "get ticker eps trend");
    return { data: [], error: errorMessage };
  }
};

export const getTickerGrowthEstimates = async (ticker) => {
  try {
    const response = await api.get(`/api/analysts/${ticker}/growth-estimates`);
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(error, "get ticker growth estimates");
    return { data: [], error: errorMessage };
  }
};

export const getTickerAnalystRecommendations = async (ticker) => {
  try {
    const response = await api.get(`/api/analysts/${ticker}/recommendations`);
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(
      error,
      "get ticker analyst recommendations"
    );
    return { data: [], error: errorMessage };
  }
};

export const getAnalystOverview = async (ticker) => {
  try {
    const response = await api.get(`/api/analysts/${ticker}/overview`);
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, false);
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(error, "get analyst overview");
    return { data: null, error: errorMessage };
  }
};

export const getFinancialStatements = async (ticker, period = "annual") => {
  try {
    const response = await api.get(
      `/api/financials/${ticker}/statements?period=${period}`
    );
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(error, "get financial statements");
    return { data: [], error: errorMessage };
  }
};

export const getIncomeStatement = async (ticker, period = "annual") => {
  try {
    const response = await api.get(
      `/api/financials/${ticker}/income-statement?period=${period}`
    );
    const result = normalizeApiResponse(response, true);
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(error, "get income statement");
    return { data: [], error: errorMessage };
  }
};

export const getCashFlowStatement = async (ticker, period = "annual") => {
  try {
    const response = await api.get(
      `/api/financials/${ticker}/cash-flow?period=${period}`
    );
    const result = normalizeApiResponse(response, true);
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(error, "get cash flow statement");
    return { data: [], error: errorMessage };
  }
};

export const getBalanceSheet = async (ticker, period = "annual") => {
  try {
    const response = await api.get(
      `/api/financials/${ticker}/balance-sheet?period=${period}`
    );
    const result = normalizeApiResponse(response, true);
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(error, "get balance sheet");
    return { data: [], error: errorMessage };
  }
};

export const getKeyMetrics = async (ticker) => {
  try {
    const url = `/api/financials/${ticker}/key-metrics`;
    const response = await api.get(url, {
      baseURL: currentConfig.baseURL,
    });
    const result = normalizeApiResponse(response, false);
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(error, `get key metrics for ${ticker}`);
    return { data: null, error: errorMessage };
  }
};

export const getAllFinancialData = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        queryParams.append(key, value);
      }
    });
    const response = await api.get(
      `/api/financials/all?${queryParams.toString()}`
    );
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(error, "get all financial data");
    return { data: [], error: errorMessage };
  }
};

export const getFinancialMetrics = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        queryParams.append(key, value);
      }
    });
    const response = await api.get(
      `/api/financials/metrics?${queryParams.toString()}`
    );
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(error, "get financial metrics");
    return { data: [], error: errorMessage };
  }
};

export const getEpsRevisions = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        queryParams.append(key, value);
      }
    });
    const response = await api.get(
      `/api/analysts/eps-revisions?${queryParams.toString()}`
    );
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(error, "get EPS revisions");
    return { data: [], error: errorMessage };
  }
};

export const getEpsTrend = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        queryParams.append(key, value);
      }
    });
    const response = await api.get(
      `/api/analysts/eps-trend?${queryParams.toString()}`
    );
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(error, "get EPS trend");
    return { data: [], error: errorMessage };
  }
};

export const getGrowthEstimates = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        queryParams.append(key, value);
      }
    });
    const response = await api.get(
      `/api/analysts/growth-estimates?${queryParams.toString()}`
    );
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(error, "get growth estimates");
    return { data: [], error: errorMessage };
  }
};

export const getEconomicData = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        queryParams.append(key, value);
      }
    });
    const response = await api.get(
      `/api/economic/data?${queryParams.toString()}`
    );
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(error, "get economic data");
    return { data: [], error: errorMessage };
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
    console.error(`❌ [API] Technical history error for ${symbol}:`, {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw new Error(
      handleApiError(error, `Failed to fetch technical history for ${symbol}`)
    );
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
    console.error(`❌ [API] Stock info error for ${symbol}:`, {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw new Error(
      handleApiError(error, `Failed to fetch stock info for ${symbol}`)
    );
  }
};

export const getStockPrice = async (symbol) => {
  console.log(`💰 [API] Fetching stock price for ${symbol}...`);
  try {
    const response = await api.get(`/stocks/price/${symbol}`);
    console.log(`💰 [API] Stock price response for ${symbol}:`, response);
    return normalizeApiResponse(response, false);
  } catch (error) {
    console.error(`❌ [API] Stock price error for ${symbol}:`, {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw new Error(
      handleApiError(error, `Failed to fetch stock price for ${symbol}`)
    );
  }
};

export const getStockHistory = async (symbol) => {
  console.log(`📊 [API] Fetching stock history for ${symbol}...`);
  try {
    const response = await api.get(`/stocks/history/${symbol}`);
    console.log(`📊 [API] Stock history response for ${symbol}:`, response);
    return normalizeApiResponse(response, true);
  } catch (error) {
    console.error(`❌ [API] Stock history error for ${symbol}:`, {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw new Error(
      handleApiError(error, `Failed to fetch stock history for ${symbol}`)
    );
  }
};

export const searchStocks = async (query) => {
  console.log(`🔍 [API] Searching stocks with query: ${query}...`);
  try {
    const response = await api.get(
      `/stocks/search?q=${encodeURIComponent(query)}`
    );
    console.log(`🔍 [API] Stock search response:`, response);
    return normalizeApiResponse(response, true);
  } catch (error) {
    console.error(`❌ [API] Stock search error:`, {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw new Error(handleApiError(error, "Failed to search stocks"));
  }
};

// --- HEALTH CHECK ---
export const getHealth = async () => {
  console.log("🏥 [API] Checking API health...");
  try {
    const response = await api.get("/health");
    console.log("🏥 [API] Health check response:", response);
    return normalizeApiResponse(response, false);
  } catch (error) {
    console.error("❌ [API] Health check error:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw new Error(handleApiError(error, "Failed to check API health"));
  }
};

// Add missing functions that are referenced in export default
export const getNaaimData = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        queryParams.append(key, value);
      }
    });
    const response = await api.get(
      `/api/market/naaim?${queryParams.toString()}`
    );
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true); // Array of NAAIM data
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(error, "get NAAIM data");
    return { data: [], error: errorMessage };
  }
};

export const getFearGreedData = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        queryParams.append(key, value);
      }
    });
    const response = await api.get(
      `/api/market/fear-greed?${queryParams.toString()}`
    );
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true); // Array of fear/greed data
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(error, "get fear & greed data");
    return { data: [], error: errorMessage };
  }
};

// Get price history data from price_daily/weekly/monthly tables
export const getPriceHistory = async (timeframe = "daily", params = {}) => {
  console.log(
    `📈 [API] Fetching price history for timeframe: ${timeframe}`,
    params
  );

  try {
    const queryParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        queryParams.append(key, value);
      }
    });

    // Use the correct endpoint for our API
    const endpoints = [
      `/api/price/history/${timeframe}?${queryParams.toString()}`,
    ];

    let response = null;
    let lastError = null;

    for (const endpoint of endpoints) {
      try {
        console.log(`📈 [API] Trying price history endpoint: ${endpoint}`);
        response = await api.get(endpoint);
        console.log(
          `📈 [API] SUCCESS with price history endpoint: ${endpoint}`,
          response
        );
        break;
      } catch (err) {
        console.log(
          `📈 [API] FAILED price history endpoint: ${endpoint}`,
          err.message
        );
        lastError = err;
        continue;
      }
    }

    if (!response) {
      console.error("📈 [API] All price history endpoints failed:", lastError);
      throw lastError;
    }

    console.log("📈 [API] Price history raw response:", response?.data);

    // Handle backend response structure: { success: true, data: [...], pagination: {...} }
    if (
      response?.data &&
      response?.data.success &&
      Array.isArray(response?.data.data)
    ) {
      console.log("📈 [API] Price history backend structure:", response?.data);
      return {
        data: response?.data.data,
        pagination: response?.data.pagination,
        statistics: response?.data.statistics,
        metadata: response?.data.metadata,
      };
    }

    // Fallback: normalize the response
    const normalizedData = normalizeApiResponse(response, true);
    return {
      data: normalizedData,
      pagination: response?.data?.pagination || null,
      statistics: response?.data?.statistics || null,
      metadata: response?.data?.metadata || null,
    };
  } catch (error) {
    console.error("❌ [API] Price history error details:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    const errorMessage = handleApiError(error, "get price history");
    return {
      data: [],
      error: errorMessage,
      pagination: null,
      timestamp: new Date().toISOString(),
    };
  }
};

// Patch all API methods to always return normalizeApiResponse
export const getTechnicalData = async (timeframe = "daily", params = {}) => {
  try {
    const queryParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        queryParams.append(key, value);
      }
    });

    // Use the correct primary endpoint based on backend routes
    const endpoint = `/api/technical/${timeframe}?${queryParams.toString()}`;
    const response = await api.get(endpoint);

    // Handle backend response structure: { success: true, data: [...], pagination: {...} }
    if (
      response?.data &&
      response?.data.success &&
      Array.isArray(response?.data.data)
    ) {
      return {
        data: response?.data.data,
        pagination: response?.data.pagination || {},
        metadata: response?.data.metadata || {},
        success: true,
        ...response?.data,
      };
    }

    // Handle case where response?.data is directly an array
    if (Array.isArray(response?.data)) {
      return {
        data: response?.data,
        pagination: {},
        metadata: {},
        success: true,
        timestamp: new Date().toISOString(),
      };
    }

    // Fallback to normalized response
    const result = normalizeApiResponse(response, true);
    return {
      data: result,
      pagination: {},
      metadata: {},
      success: true,
      timestamp: new Date().toISOString(),
    };
  } catch (error) {
    const errorMessage = handleApiError(error, "get technical data");
    return {
      data: [],
      pagination: {},
      metadata: {},
      success: false,
      error: errorMessage,
      timestamp: new Date().toISOString(),
    };
  }
};

export const getTechnicalSummary = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        queryParams.append(key, value);
      }
    });
    const response = await api.get(
      `/api/technical/summary?${queryParams.toString()}`
    );
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(error, "get technical summary");
    return { data: [], error: errorMessage };
  }
};

export const getEarningsMetrics = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        queryParams.append(key, value);
      }
    });
    const response = await api.get(
      `/api/calendar/earnings-metrics?${queryParams.toString()}`
    );
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    return { data: result };
  } catch (error) {
    const errorMessage = handleApiError(error, "get earnings metrics");
    return { data: [], error: errorMessage };
  }
};

// Test API Connection
export const initializeApi = async () => {
  try {
    console.log("🔧 [API] Initializing API connection...");
    const healthResponse = await fetch(`${getCurrentBaseURL()}/health`, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
      },
    });

    if (!healthResponse.ok) {
      throw new Error(`API initialization failed: ${healthResponse.status}`);
    }

    const healthData = await healthResponse.json();
    console.log("✅ [API] API initialized successfully:", healthData);
    return healthData;
  } catch (error) {
    console.error("❌ [API] API initialization failed:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw error;
  }
};

export const testApiConnection = async (customUrl = null) => {
  try {
    console.log("Testing API connection...");
    console.log("Current API URL:", currentConfig.baseURL);
    console.log("Custom URL:", customUrl);
    console.log("Environment:", import.meta.env.MODE);
    console.log("VITE_API_URL:", import.meta.env.VITE_API_URL);
    const testUrl = customUrl || currentConfig.baseURL;
    const response = await api.get("/api/health?quick=true", {
      baseURL: testUrl,
      timeout: 7000,
    });
    return {
      success: true,
      apiUrl: testUrl,
      status: response.status,
      data: response?.data,
      message: "API connection successful",
    };
  } catch (error) {
    console.error("API connection test failed:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
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
        fullUrl:
          (customUrl || currentConfig.baseURL) + "/api/health?quick=true",
      },
    };
  }
};

// Diagnostic function for ServiceHealth
export const getDiagnosticInfo = () => {
  return {
    currentApiUrl: currentConfig.baseURL,
    axiosDefaultBaseUrl: api.defaults.baseURL,
    viteApiUrl: import.meta.env.VITE_API_URL,
    isConfigured: currentConfig.isConfigured,
    environment: import.meta.env.MODE,
    urlsMatch: currentConfig.baseURL === api.defaults.baseURL,
    timestamp: new Date().toISOString(),
  };
};

// Database health (full details)
export const getDatabaseHealthFull = async () => {
  try {
    const response = await api.get("/api/health/database", {
      baseURL: currentConfig.baseURL,
    });
    // Return the full response (healthSummary, tables, etc.)
    return { data: response?.data };
  } catch (error) {
    const errorMessage = handleApiError(error, "get database health");
    return { data: null, error: errorMessage };
  }
};

// Health check (robust: tries /health, then /)
export const healthCheck = async (queryParams = "") => {
  let triedRoot = false;
  let healthUrl = `/api/health${queryParams}`;
  let rootUrl = `/${queryParams}`;
  try {
    const response = await api.get(healthUrl, {
      baseURL: currentConfig.baseURL,
    });
    console.log("Health check response:", response?.data);
    return {
      data: response?.data,
      healthy: true,
      endpoint: healthUrl,
      fallback: false,
      timestamp: new Date().toISOString(),
    };
  } catch (error) {
    // If 404 or network error, try root endpoint
    console.warn(
      "Health check failed for /api/health, trying root / endpoint..."
    );
    triedRoot = true;
    try {
      const response = await api.get(rootUrl, {
        baseURL: currentConfig.baseURL,
      });
      console.log("Root endpoint health check response:", response?.data);
      return {
        data: response?.data,
        healthy: true,
        endpoint: rootUrl,
        fallback: true,
        timestamp: new Date().toISOString(),
      };
    } catch (rootError) {
      console.error(
        "Error in health check (both endpoints failed):",
        rootError
      );
      const errorMessage = handleApiError(
        rootError,
        "health check (both endpoints)"
      );
      return {
        data: null,
        error: errorMessage,
        healthy: false,
        endpoint: triedRoot ? rootUrl : healthUrl,
        fallback: triedRoot,
        timestamp: new Date().toISOString(),
      };
    }
  }
};

// Data validation functions
export const getDataValidationSummary = async () => {
  try {
    const response = await api.get("/api/health/full");
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, false);
    return { data: result };
  } catch (error) {
    console.error("Error fetching data validation summary:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw error;
  }
};

// Get comprehensive stock price history - BULLETPROOF VERSION
export const getStockPriceHistory = async (ticker, limit = 90) => {
  try {
    console.log(
      `BULLETPROOF: Fetching price history for ${ticker} with limit ${limit}`
    );
    const response = await api.get(
      `/api/stocks/${ticker}/prices?limit=${limit}`
    );
    console.log(
      `BULLETPROOF: Price history response received for ${ticker}:`,
      response?.data
    );
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true); // Expect array of price data
    return { data: result };
  } catch (error) {
    console.error("BULLETPROOF: Error fetching stock price history:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    // Use the centralized error handler for consistent error messaging
    throw handleApiError(error, `Failed to fetch price history for ${ticker}`);
  }
};

export const getRecentAnalystActions = async (limit = 10) => {
  try {
    const response = await api.get(
      `/api/analysts/recent-actions?limit=${limit}`
    );
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true); // Expect array of analyst actions
    return {
      data: result,
      summary: { date: null, total_actions: 0, upgrades: 0, downgrades: 0 },
    };
  } catch (error) {
    const errorMessage = handleApiError(error, "get recent analyst actions");
    return {
      data: [],
      summary: { date: null, total_actions: 0, upgrades: 0, downgrades: 0 },
      error: errorMessage,
    };
  }
};

// Simple API test function
export const testApiEndpoints = async () => {
  const results = {};

  try {
    // Test basic health check
    const healthResponse = await api.get("/api/health");
    results.health = { success: true, data: healthResponse?.data };
  } catch (error) {
    results.health = { success: false, error: error.message };
  }

  try {
    // Test stocks endpoint
    const stocksResponse = await api.get("/api/stocks?limit=5");
    results.stocks = { success: true, data: stocksResponse?.data };
  } catch (error) {
    results.stocks = { success: false, error: error.message };
  }

  try {
    // Test technical data endpoint
    const technicalResponse = await api.get("/api/technical/daily?limit=5");
    results.technical = { success: true, data: technicalResponse?.data };
  } catch (error) {
    results.technical = { success: false, error: error.message };
  }

  try {
    // Test market overview endpoint
    const marketResponse = await api.get("/api/market/overview");
    results.market = { success: true, data: marketResponse?.data };
  } catch (error) {
    results.market = { success: false, error: error.message };
  }

  console.log("API Test Results:", results);
  return results;
};

// Market indices
export const getMarketIndices = async () => {
  console.log("🚀 getMarketIndices: Starting API call...");
  try {
    const response = await api.get("/api/market/indices");

    console.log("📊 getMarketIndices: Raw response:", {
      status: response.status,
      hasData: !!response?.data,
      dataType: typeof response?.data,
      dataKeys: response?.data ? Object.keys(response?.data) : [],
    });

    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    console.log("✅ getMarketIndices: returning result:", result);
    return { data: result };
  } catch (error) {
    console.error("❌ Error fetching market indices:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      url: error.config?.url
    });
    const errorMessage = handleApiError(error, "get market indices");
    return { data: [], error: errorMessage };
  }
};

// Sector performance
export const getSectorPerformance = async () => {
  console.log("🚀 getSectorPerformance: Starting API call...");
  try {
    const response = await api.get("/api/market/sectors");

    console.log("📊 getSectorPerformance: Raw response:", {
      status: response.status,
      hasData: !!response?.data,
      dataType: typeof response?.data,
      dataKeys: response?.data ? Object.keys(response?.data) : [],
    });

    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    console.log("✅ getSectorPerformance: returning result:", result);
    return { data: result };
  } catch (error) {
    console.error("❌ Error fetching sector performance:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      url: error.config?.url
    });
    const errorMessage = handleApiError(error, "get sector performance");
    return { data: [], error: errorMessage };
  }
};

// Market volatility
export const getMarketVolatility = async () => {
  console.log("🚀 getMarketVolatility: Starting API call...");
  try {
    const response = await api.get("/api/market/volatility");

    console.log("📊 getMarketVolatility: Raw response:", {
      status: response.status,
      hasData: !!response?.data,
      dataType: typeof response?.data,
      dataKeys: response?.data ? Object.keys(response?.data) : [],
    });

    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    console.log("✅ getMarketVolatility: returning result:", result);
    return { data: result };
  } catch (error) {
    console.error("❌ Error fetching market volatility:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    const errorMessage = handleApiError(error, "get market volatility");
    return { data: [], error: errorMessage };
  }
};

// Economic calendar
export const getEconomicCalendar = async () => {
  console.log("🚀 getEconomicCalendar: Starting API call...");
  try {
    const response = await api.get("/api/market/calendar");

    console.log("📊 getEconomicCalendar: Raw response:", {
      status: response.status,
      hasData: !!response?.data,
      dataType: typeof response?.data,
      dataKeys: response?.data ? Object.keys(response?.data) : [],
    });

    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    console.log("✅ getEconomicCalendar: returning result:", result);
    return { data: result };
  } catch (error) {
    console.error("❌ Error fetching economic calendar:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    const errorMessage = handleApiError(error, "get economic calendar");
    return { data: [], error: errorMessage };
  }
};

// Market cap categories
export const getMarketCapCategories = async () => {
  console.log("🚀 getMarketCapCategories: Starting API call...");
  try {
    const response = await api.get("/api/stocks/market-cap-categories");

    console.log("📊 getMarketCapCategories: Raw response:", {
      status: response.status,
      hasData: !!response?.data,
      dataType: typeof response?.data,
      dataKeys: response?.data ? Object.keys(response?.data) : [],
    });

    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    console.log("✅ getMarketCapCategories: returning result:", result);
    return { data: result };
  } catch (error) {
    console.error("❌ Error fetching market cap categories:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    const errorMessage = handleApiError(error, "get market cap categories");
    return { data: [], error: errorMessage };
  }
};

// Technical indicators
export const getTechnicalIndicators = async (symbol, timeframe, indicators) => {
  console.log("🚀 getTechnicalIndicators: Starting API call...", {
    symbol,
    timeframe,
    indicators,
  });
  try {
    const response = await api.get(`/api/technical/indicators/${symbol}`, {
      params: { timeframe, indicators: indicators.join(",") },
    });

    console.log("📊 getTechnicalIndicators: Raw response:", {
      status: response.status,
      hasData: !!response?.data,
      dataType: typeof response?.data,
      dataKeys: response?.data ? Object.keys(response?.data) : [],
    });

    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    console.log("✅ getTechnicalIndicators: returning result:", result);
    return { data: result };
  } catch (error) {
    console.error("❌ Error fetching technical indicators:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    const errorMessage = handleApiError(error, "get technical indicators");
    return { data: [], error: errorMessage };
  }
};

// Volume data
export const getVolumeData = async (symbol, timeframe) => {
  console.log("🚀 getVolumeData: Starting API call...", { symbol, timeframe });
  try {
    const response = await api.get(`/api/stocks/${symbol}/volume`, {
      params: { timeframe },
    });

    console.log("📊 getVolumeData: Raw response:", {
      status: response.status,
      hasData: !!response?.data,
      dataType: typeof response?.data,
      dataKeys: response?.data ? Object.keys(response?.data) : [],
    });

    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    console.log("✅ getVolumeData: returning result:", result);
    return { data: result };
  } catch (error) {
    console.error("❌ Error fetching volume data:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    const errorMessage = handleApiError(error, "get volume data");
    return { data: [], error: errorMessage };
  }
};

// Support resistance levels
export const getSupportResistanceLevels = async (symbol) => {
  console.log("🚀 getSupportResistanceLevels: Starting API call...", {
    symbol,
  });
  try {
    const response = await api.get(
      `/api/technical/support-resistance/${symbol}`
    );

    console.log("📊 getSupportResistanceLevels: Raw response:", {
      status: response.status,
      hasData: !!response?.data,
      dataType: typeof response?.data,
      dataKeys: response?.data ? Object.keys(response?.data) : [],
    });

    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, false);
    console.log("✅ getSupportResistanceLevels: returning result:", result);
    return { data: result };
  } catch (error) {
    console.error("❌ Error fetching support resistance levels:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    const errorMessage = handleApiError(error, "get support resistance levels");
    return { data: null, error: errorMessage };
  }
};

// --- DASHBOARD API FUNCTIONS ---
export const getDashboardSummary = async () => {
  console.log("📊 [API] Fetching dashboard summary...");
  try {
    const response = await api.get("/dashboard/summary");
    console.log("📊 [API] Dashboard summary response:", response);
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, false);
    return { data: result };
  } catch (error) {
    console.error("❌ [API] Dashboard summary error:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw new Error(handleApiError(error, "Failed to fetch dashboard summary"));
  }
};

export const getDashboardPerformance = async () => {
  console.log("📈 [API] Fetching dashboard performance...");
  try {
    const response = await api.get("/dashboard/performance");
    console.log("📈 [API] Dashboard performance response:", response);
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    return { data: result };
  } catch (error) {
    console.error("❌ [API] Dashboard performance error:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw new Error(
      handleApiError(error, "Failed to fetch dashboard performance")
    );
  }
};

export const getDashboardAlerts = async () => {
  console.log("🚨 [API] Fetching dashboard alerts...");
  try {
    const response = await api.get("/dashboard/alerts");
    console.log("🚨 [API] Dashboard alerts response:", response);
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    return { data: result };
  } catch (error) {
    console.error("❌ [API] Dashboard alerts error:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw new Error(handleApiError(error, "Failed to fetch dashboard alerts"));
  }
};

export const getDashboardDebug = async () => {
  console.log("🔧 [API] Fetching dashboard debug info...");
  try {
    const response = await api.get("/dashboard/debug");
    console.log("🔧 [API] Dashboard debug response:", response);
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, false);
    return { data: result };
  } catch (error) {
    console.error("❌ [API] Dashboard debug error:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw new Error(
      handleApiError(error, "Failed to fetch dashboard debug info")
    );
  }
};

// --- MARKET API FUNCTIONS ---
export const getMarketIndicators = async () => {
  console.log("📊 [API] Fetching market indicators...");
  try {
    const response = await api.get("/market/indicators");
    console.log("📊 [API] Market indicators response:", response);
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, false);
    return { data: result };
  } catch (error) {
    console.error("❌ [API] Market indicators error:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      url: error.config?.url
    });
    throw new Error(handleApiError(error, "Failed to fetch market indicators"));
  }
};

export const getMarketSentiment = async () => {
  console.log("😊 [API] Fetching market sentiment...");
  try {
    // Mock data for now since backend endpoint might not exist
    const mockSentiment = {
      sentiment: "greed",
      value: 65,
      classification: "Greed",
      timestamp: new Date().toISOString(),
      indicators: {
        vix: 18.5,
        put_call_ratio: 0.85,
        market_momentum: 0.7,
        stock_price_strength: 0.8,
        stock_price_breadth: 0.6,
        junk_bond_demand: 0.5,
        market_volatility: 0.4,
      },
    };
    console.log("😊 [API] Returning mock market sentiment:", mockSentiment);
    return { data: mockSentiment };
  } catch (error) {
    console.error("❌ [API] Market sentiment error:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      url: error.config?.url
    });
    throw new Error(handleApiError(error, "Failed to fetch market sentiment"));
  }
};

// --- FINANCIAL DATA API FUNCTIONS ---
export const getFinancialData = async (symbol) => {
  console.log(`💰 [API] Fetching financial data for ${symbol}...`);
  try {
    const response = await api.get(`/financials/data/${symbol}`);
    console.log(`💰 [API] Financial data response for ${symbol}:`, response);
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, false);
    return { data: result };
  } catch (error) {
    console.error(`❌ [API] Financial data error for ${symbol}:`, {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      url: error.config?.url,
      symbol
    });
    throw new Error(
      handleApiError(error, `Failed to fetch financial data for ${symbol}`)
    );
  }
};

export const getEarningsData = async (symbol) => {
  console.log(`📊 [API] Fetching earnings data for ${symbol}...`);
  try {
    const response = await api.get(`/financials/earnings/${symbol}`);
    console.log(`📊 [API] Earnings data response for ${symbol}:`, response);
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    return { data: result };
  } catch (error) {
    console.error(`❌ [API] Earnings data error for ${symbol}:`, {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw new Error(
      handleApiError(error, `Failed to fetch earnings data for ${symbol}`)
    );
  }
};

export const getCashFlow = async (symbol) => {
  console.log(`💵 [API] Fetching cash flow for ${symbol}...`);
  try {
    const response = await api.get(`/financials/cash-flow/${symbol}`);
    console.log(`💵 [API] Cash flow response for ${symbol}:`, response);
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, true);
    return { data: result };
  } catch (error) {
    console.error(`❌ [API] Cash flow error for ${symbol}:`, {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw new Error(
      handleApiError(error, `Failed to fetch cash flow for ${symbol}`)
    );
  }
};

// --- MISSING DASHBOARD API FUNCTIONS ---
export const getDashboardUser = async () => {
  console.log("👤 [API] Fetching dashboard user...");
  try {
    // Mock data for now since backend endpoint doesn't exist
    const mockUser = {
      id: 1,
      name: "John Doe",
      email: "john.doe@edgebrooke.com",
      role: "trader",
      lastLogin: new Date().toISOString(),
    };
    console.log("👤 [API] Returning mock user data:", mockUser);
    return { data: mockUser };
  } catch (error) {
    console.error("❌ [API] Dashboard user error:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw new Error(handleApiError(error, "Failed to fetch dashboard user"));
  }
};

export const getDashboardWatchlist = async () => {
  console.log("👀 [API] Fetching dashboard watchlist...");
  try {
    // Mock data for now since backend endpoint doesn't exist
    const mockWatchlist = [
      {
        symbol: "AAPL",
        name: "Apple Inc.",
        price: 150.25,
        change: 2.15,
        changePercent: 1.45,
      },
      {
        symbol: "MSFT",
        name: "Microsoft Corp.",
        price: 320.5,
        change: -1.2,
        changePercent: -0.37,
      },
      {
        symbol: "GOOGL",
        name: "Alphabet Inc.",
        price: 2750.0,
        change: 15.5,
        changePercent: 0.57,
      },
      {
        symbol: "TSLA",
        name: "Tesla Inc.",
        price: 850.75,
        change: 25.3,
        changePercent: 3.06,
      },
      {
        symbol: "NVDA",
        name: "NVIDIA Corp.",
        price: 450.25,
        change: 8.75,
        changePercent: 1.98,
      },
    ];
    console.log("👀 [API] Returning mock watchlist data:", mockWatchlist);
    return { data: mockWatchlist };
  } catch (error) {
    console.error("❌ [API] Dashboard watchlist error:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw new Error(
      handleApiError(error, "Failed to fetch dashboard watchlist")
    );
  }
};

export const getDashboardPortfolio = async () => {
  console.log("💼 [API] Fetching dashboard portfolio...");
  try {
    // Mock data for now since backend endpoint doesn't exist
    const mockPortfolio = {
      value: 1250000,
      pnl: {
        daily: 12500,
        mtd: 45000,
        ytd: 180000,
      },
      positions: [
        {
          symbol: "AAPL",
          shares: 100,
          avgPrice: 145.0,
          currentPrice: 150.25,
          marketValue: 15025,
          pnl: 525,
          pnlPercent: 3.62,
        },
        {
          symbol: "MSFT",
          shares: 50,
          avgPrice: 315.0,
          currentPrice: 320.5,
          marketValue: 16025,
          pnl: 275,
          pnlPercent: 1.75,
        },
        {
          symbol: "GOOGL",
          shares: 25,
          avgPrice: 2700.0,
          currentPrice: 2750.0,
          marketValue: 68750,
          pnl: 1250,
          pnlPercent: 1.85,
        },
      ],
    };
    console.log("💼 [API] Returning mock portfolio data:", mockPortfolio);
    return { data: mockPortfolio };
  } catch (error) {
    console.error("❌ [API] Dashboard portfolio error:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw new Error(
      handleApiError(error, "Failed to fetch dashboard portfolio")
    );
  }
};

export const getDashboardPortfolioMetrics = async () => {
  console.log("📊 [API] Fetching dashboard portfolio metrics...");
  try {
    // Mock data for now since backend endpoint doesn't exist
    const mockMetrics = {
      sharpe: 1.85,
      beta: 0.92,
      maxDrawdown: 0.08,
      volatility: 0.15,
      alpha: 0.045,
      informationRatio: 1.2,
    };
    console.log("📊 [API] Returning mock portfolio metrics:", mockMetrics);
    return { data: mockMetrics };
  } catch (error) {
    console.error("❌ [API] Dashboard portfolio metrics error:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw new Error(
      handleApiError(error, "Failed to fetch dashboard portfolio metrics")
    );
  }
};

export const getDashboardHoldings = async () => {
  console.log("📈 [API] Fetching dashboard holdings...");
  try {
    // Mock data for now since backend endpoint doesn't exist
    const mockHoldings = [
      {
        symbol: "AAPL",
        shares: 100,
        avgPrice: 145.0,
        currentPrice: 150.25,
        marketValue: 15025,
        pnl: 525,
        pnlPercent: 3.62,
      },
      {
        symbol: "MSFT",
        shares: 50,
        avgPrice: 315.0,
        currentPrice: 320.5,
        marketValue: 16025,
        pnl: 275,
        pnlPercent: 1.75,
      },
      {
        symbol: "GOOGL",
        shares: 25,
        avgPrice: 2700.0,
        currentPrice: 2750.0,
        marketValue: 68750,
        pnl: 1250,
        pnlPercent: 1.85,
      },
      {
        symbol: "TSLA",
        shares: 75,
        avgPrice: 800.0,
        currentPrice: 850.75,
        marketValue: 63806,
        pnl: 3806,
        pnlPercent: 6.34,
      },
      {
        symbol: "NVDA",
        shares: 30,
        avgPrice: 420.0,
        currentPrice: 450.25,
        marketValue: 13508,
        pnl: 908,
        pnlPercent: 7.21,
      },
    ];
    console.log("📈 [API] Returning mock holdings data:", mockHoldings);
    return { data: mockHoldings };
  } catch (error) {
    console.error("❌ [API] Dashboard holdings error:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw new Error(
      handleApiError(error, "Failed to fetch dashboard holdings")
    );
  }
};

export const getDashboardUserSettings = async () => {
  console.log("⚙️ [API] Fetching dashboard user settings...");
  try {
    // Mock data for now since backend endpoint doesn't exist
    const mockSettings = {
      theme: "light",
      notifications: true,
      refreshInterval: 30000,
      defaultSymbol: "AAPL",
      chartType: "candlestick",
      timezone: "America/New_York",
    };
    console.log("⚙️ [API] Returning mock user settings:", mockSettings);
    return { data: mockSettings };
  } catch (error) {
    console.error("❌ [API] Dashboard user settings error:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw new Error(
      handleApiError(error, "Failed to fetch dashboard user settings")
    );
  }
};

export const getDashboardMarketSummary = async () => {
  console.log("📈 [API] Fetching dashboard market summary...");
  try {
    // Mock data for now since backend endpoint doesn't exist
    const mockMarketSummary = {
      indices: [
        {
          symbol: "SPY",
          name: "S&P 500",
          value: 4500.25,
          change: 15.5,
          changePercent: 0.35,
        },
        {
          symbol: "QQQ",
          name: "NASDAQ 100",
          value: 3800.75,
          change: 25.3,
          changePercent: 0.67,
        },
        {
          symbol: "DIA",
          name: "Dow Jones",
          value: 35000.5,
          change: 125.75,
          changePercent: 0.36,
        },
      ],
      indicators: [
        { name: "VIX", value: 18.5, change: -0.5 },
        { name: "Put/Call Ratio", value: 0.85, change: 0.05 },
        { name: "Advance/Decline", value: 1.2, change: 0.1 },
      ],
    };
    console.log("📈 [API] Returning mock market summary:", mockMarketSummary);
    return { data: mockMarketSummary };
  } catch (error) {
    console.error("❌ [API] Dashboard market summary error:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw new Error(
      handleApiError(error, "Failed to fetch dashboard market summary")
    );
  }
};

export const getDashboardEarningsCalendar = async () => {
  console.log("📅 [API] Fetching dashboard earnings calendar...");
  try {
    // Mock data for now since backend endpoint doesn't exist
    const mockEarnings = [
      {
        symbol: "AAPL",
        company_name: "Apple Inc.",
        date: "2024-01-25",
        time: "AMC",
        importance: "high",
      },
      {
        symbol: "MSFT",
        company_name: "Microsoft Corp.",
        date: "2024-01-30",
        time: "AMC",
        importance: "high",
      },
      {
        symbol: "GOOGL",
        company_name: "Alphabet Inc.",
        date: "2024-02-01",
        time: "AMC",
        importance: "medium",
      },
      {
        symbol: "TSLA",
        company_name: "Tesla Inc.",
        date: "2024-02-05",
        time: "AMC",
        importance: "high",
      },
      {
        symbol: "NVDA",
        company_name: "NVIDIA Corp.",
        date: "2024-02-08",
        time: "AMC",
        importance: "high",
      },
    ];
    console.log("📅 [API] Returning mock earnings calendar:", mockEarnings);
    return { data: mockEarnings };
  } catch (error) {
    console.error("❌ [API] Dashboard earnings calendar error:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw new Error(
      handleApiError(error, "Failed to fetch dashboard earnings calendar")
    );
  }
};

export const getDashboardAnalystInsights = async () => {
  console.log("🧠 [API] Fetching dashboard analyst insights...");
  try {
    // Mock data for now since backend endpoint doesn't exist
    const mockInsights = {
      upgrades: [
        {
          symbol: "AAPL",
          analyst: "Goldman Sachs",
          action: "Upgrade",
          from: "Neutral",
          to: "Buy",
          price_target: 175,
        },
        {
          symbol: "MSFT",
          analyst: "Morgan Stanley",
          action: "Upgrade",
          from: "Equal Weight",
          to: "Overweight",
          price_target: 350,
        },
      ],
      downgrades: [
        {
          symbol: "TSLA",
          analyst: "JP Morgan",
          action: "Downgrade",
          from: "Overweight",
          to: "Neutral",
          price_target: 800,
        },
      ],
    };
    console.log("🧠 [API] Returning mock analyst insights:", mockInsights);
    return { data: mockInsights };
  } catch (error) {
    console.error("❌ [API] Dashboard analyst insights error:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw new Error(
      handleApiError(error, "Failed to fetch dashboard analyst insights")
    );
  }
};

export const getDashboardFinancialHighlights = async () => {
  console.log("💰 [API] Fetching dashboard financial highlights...");
  try {
    // Mock data for now since backend endpoint doesn't exist
    const mockHighlights = [
      { label: "Revenue Growth", value: "+12.5%" },
      { label: "EPS Growth", value: "+8.2%" },
      { label: "Profit Margin", value: "18.5%" },
      { label: "ROE", value: "22.3%" },
      { label: "Debt/Equity", value: "0.45" },
      { label: "Current Ratio", value: "1.8" },
    ];
    console.log(
      "💰 [API] Returning mock financial highlights:",
      mockHighlights
    );
    return { data: mockHighlights };
  } catch (error) {
    console.error("❌ [API] Dashboard financial highlights error:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw new Error(
      handleApiError(error, "Failed to fetch dashboard financial highlights")
    );
  }
};

export const getDashboardSymbols = async () => {
  console.log("🔤 [API] Fetching dashboard symbols...");
  try {
    // Mock data for now since backend endpoint doesn't exist
    const mockSymbols = [
      "AAPL",
      "MSFT",
      "GOOGL",
      "TSLA",
      "NVDA",
      "SPY",
      "QQQ",
      "DIA",
      "AMZN",
      "META",
    ];
    console.log("🔤 [API] Returning mock symbols:", mockSymbols);
    return { data: mockSymbols };
  } catch (error) {
    console.error("❌ [API] Dashboard symbols error:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw new Error(handleApiError(error, "Failed to fetch dashboard symbols"));
  }
};

export const getTradingSignalsDaily = async (params = {}) => {
  console.log("📈 [API] Fetching daily trading signals...", params);
  
  try {
    const queryParams = new URLSearchParams({
      limit: params.limit || 10,
      ...params
    }).toString();
    
    // Try multiple endpoint variations
    const endpoints = [`/trading/signals/daily?${queryParams}`, `/api/trading/signals/daily?${queryParams}`];
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
      console.error("📈 [API] All endpoints failed, throwing last error:", lastError);
      throw lastError;
    }

    console.log("📈 [API] Trading signals daily raw response:", response);
    const result = normalizeApiResponse(response, false);
    console.log("📈 [API] Trading signals daily normalized result:", result);
    return { data: result };
  } catch (error) {
    console.error("❌ [API] Trading signals daily error details:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText,
      url: error.config?.url,
      method: error.config?.method,
      stack: error?.stack?.substring(0, 500) + "..."
    });
    throw new Error(handleApiError(error, "Failed to fetch daily trading signals"));
  }
};

export const getCurrentUser = async () => {
  console.log("👤 [API] Fetching current user info...");
  
  try {
    // Try multiple endpoint variations
    const endpoints = ["/api/auth/me"];
    let response = null;
    let lastError = null;

    for (const endpoint of endpoints) {
      try {
        console.log(`👤 [API] Trying endpoint: ${endpoint}`);
        response = await api.get(endpoint);
        console.log(`👤 [API] SUCCESS with endpoint: ${endpoint}`, response);
        break;
      } catch (err) {
        console.log(`👤 [API] FAILED endpoint: ${endpoint}`, err.message);
        lastError = err;
        continue;
      }
    }

    if (!response) {
      console.error("👤 [API] All endpoints failed, throwing last error:", lastError);
      throw lastError;
    }

    console.log("👤 [API] Current user raw response:", response);
    const result = normalizeApiResponse(response, false);
    console.log("👤 [API] Current user normalized result:", result);
    return { data: result };
  } catch (error) {
    console.error("❌ [API] Current user error details:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText,
      url: error.config?.url,
      method: error.config?.method,
      stack: error?.stack?.substring(0, 500) + "..."
    });
    throw new Error(handleApiError(error, "Failed to fetch current user"));
  }
};

export const getDashboardTechnicalSignals = async () => {
  console.log("📊 [API] Fetching dashboard technical signals...");
  try {
    // Mock data for now since backend endpoint doesn't exist
    const mockSignals = [
      {
        symbol: "AAPL",
        signal: "Buy",
        date: "2024-01-20",
        current_price: 150.25,
        performance_percent: 2.15,
      },
      {
        symbol: "MSFT",
        signal: "Buy",
        date: "2024-01-19",
        current_price: 320.5,
        performance_percent: 1.75,
      },
      {
        symbol: "GOOGL",
        signal: "Sell",
        date: "2024-01-18",
        current_price: 2750.0,
        performance_percent: -0.85,
      },
      {
        symbol: "TSLA",
        signal: "Buy",
        date: "2024-01-17",
        current_price: 850.75,
        performance_percent: 3.25,
      },
      {
        symbol: "NVDA",
        signal: "Buy",
        date: "2024-01-16",
        current_price: 450.25,
        performance_percent: 4.1,
      },
    ];
    console.log("📊 [API] Returning mock technical signals:", mockSignals);
    return { data: mockSignals };
  } catch (error) {
    console.error("❌ [API] Dashboard technical signals error:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw new Error(
      handleApiError(error, "Failed to fetch dashboard technical signals")
    );
  }
};

// Missing API functions that tests expect
export const getQuote = async (symbol) => {
  try {
    console.log(`📊 [API] Fetching quote for ${symbol}...`);
    const response = await api.get(`/api/market/quote/${symbol}`);

    const result = {
      symbol: symbol,
      price: response?.data?.price || 0,
      change: response?.data?.change || 0,
      changePercent: response?.data?.changePercent || 0,
      volume: response?.data?.volume || 0,
      timestamp: response?.data?.timestamp || new Date().toISOString(),
    };

    console.log(`📊 [API] Quote for ${symbol}:`, result);
    return result;
  } catch (error) {
    console.error(`❌ [API] Quote error for ${symbol}:`, {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw new Error(`Failed to fetch quote for ${symbol}: ${error?.message || 'Unknown error'}`);
  }
};

export const placeOrder = async (orderRequest) => {
  try {
    console.log("📈 [API] Placing order:", orderRequest);
    const response = await api.post("/api/orders", orderRequest);

    const result = {
      orderId: response?.data?.orderId || `order-${Date.now()}`,
      status: response?.data?.status || "pending",
      symbol: orderRequest.symbol,
      quantity: orderRequest.quantity,
      side: orderRequest.side,
      type: orderRequest.type || "market",
      timestamp: new Date().toISOString(),
    };

    console.log("📈 [API] Order placed:", result);
    return result;
  } catch (error) {
    console.error("❌ [API] Order placement error:", {
      message: error?.message || 'Unknown error',
      status: error.response?.status,
      statusText: error.response?.statusText
    });
    throw new Error(`Failed to place order: ${error?.message || 'Unknown error'}`);
  }
};

// AI Chat functions for EnhancedAIChat component
export const sendChatMessage = async (message, options = {}) => {
  try {
    const response = await api.post('/api/ai/chat', {
      message,
      ...options
    });
    return response?.data;
  } catch (error) {
    console.error('Failed to send chat message:', error);
    throw new Error(handleApiError(error, "Failed to send chat message"));
  }
};

export const clearChatHistory = async () => {
  try {
    const response = await api.delete('/api/ai/chat/history');
    return response?.data;
  } catch (error) {
    console.error('Failed to clear chat history:', error);
    throw new Error(handleApiError(error, "Failed to clear chat history"));
  }
};

// Export all methods as a default object for easier importing
export default {
  // Core API
  healthCheck,
  getMarketOverview,

  // Portfolio functions (with aliases for tests)
  getPortfolio: getPortfolioData, // Alias for tests
  getPortfolioData,
  getMarketSentimentHistory,
  getMarketSectorPerformance,
  getMarketBreadth,
  getEconomicIndicators,
  getSeasonalityData,
  getMarketResearchIndicators,
  getPortfolioAnalytics,
  getPortfolioRiskAnalysis,
  getPortfolioOptimization,
  addHolding,
  updateHolding,
  deleteHolding,
  importPortfolioFromBroker,
  getPortfolioPerformance,
  getBenchmarkData,
  getPortfolioOptimizationData,
  runPortfolioOptimization,
  getRebalancingRecommendations,
  getRiskAnalysis,
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
  initializeApi,
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
  getDashboardDebug,
  getMarketIndicators,
  getMarketSentiment,
  getFinancialData,
  getEarningsData,
  getCashFlow,
  getTechnicalHistory,
  getStockInfo,
  getStockPrice,
  getStockHistory,
  searchStocks,
  getHealth,

  // API Key management
  getApiKeys,
  addApiKey,
  updateApiKey,
  deleteApiKey,

  // Trading functions
  placeOrder,
  getQuote,

  // AI Chat functions
  sendChatMessage,
  clearChatHistory,

  // Generic HTTP methods for direct API calls
  get: (url, config) => api.get(url, config),
  post: (url, data, config) => api.post(url, data, config),
  put: (url, data, config) => api.put(url, data, config),
  delete: (url, config) => api.delete(url, config),
  patch: (url, data, config) => api.patch(url, data, config),
};
