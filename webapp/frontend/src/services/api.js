import axios from "axios";
import { tokenManager } from "./tokenManager";
import dataCache from "./dataCache";

// Get API configuration
export const getApiConfig = () => {
  // STRICT 3-LEVEL URL RESOLUTION - no hardcoded production URLs
  // 1. Runtime injection (AWS deployment) - check if __CONFIG__ exists, not just if API_URL is truthy
  // This allows empty string for localhost development
  if (typeof window !== "undefined" && window.__CONFIG__ && 'API_URL' in window.__CONFIG__) {
    const apiUrl = window.__CONFIG__.API_URL;
    // Empty API_URL means local dev with Vite proxy — not serverless
    if (!apiUrl) {
      return { baseURL: "", apiUrl: "", isServerless: false, isDev: true, isDevelopment: true, isProduction: false };
    }
    return { baseURL: apiUrl, apiUrl, isServerless: !apiUrl.includes("localhost"), isDev: false, isDevelopment: false, isProduction: true };
  }

  // 2. Build-time env var
  if (import.meta.env?.VITE_API_URL) {
    const apiUrl = import.meta.env.VITE_API_URL;
    return { baseURL: apiUrl, apiUrl, isServerless: !apiUrl.includes("localhost"), isDev: false, isDevelopment: true, isProduction: false };
  }

  // 3. Dev: relative path, Vite proxy handles it
  const isDev = import.meta.env?.DEV;
  const apiUrl = "";

  const config = {
    baseURL: apiUrl,
    apiUrl: apiUrl,
    isServerless: false,
    isDev: isDev,
    isDevelopment: isDev,
    isProduction: false,
  };

  // Log if API URL is not available in production
  if (!config.baseURL && !isDev) {
    console.error('[API CONFIG ERROR] No API URL available. Check: window.__CONFIG__.API_URL, VITE_API_URL, or falling back to localhost');
  }

  return config;
};

// Create API instance that can be updated
let currentConfig = getApiConfig();

// Initialize and watch for config changes (config.js may load after module init in production)
export const initializeApiConfig = () => {
  const newConfig = getApiConfig();
  if (newConfig.baseURL !== currentConfig.baseURL) {
    console.log(`[API] Config updated: baseURL changed from "${currentConfig.baseURL}" to "${newConfig.baseURL}"`);
    currentConfig = newConfig;
    api.defaults.baseURL = newConfig.baseURL;
  }
};

// If window.__CONFIG__ gets set after module init (due to Vite reordering), reinitialize on first use
// Set up a timer to check if config has been loaded
if (typeof window !== "undefined") {
  let initCheckCount = 0;
  const checkConfigInit = setInterval(() => {
    initCheckCount++;
    if (typeof window !== "undefined" && window.__CONFIG__ && currentConfig.baseURL !== window.__CONFIG__.API_URL) {
      console.log(`[API] Detected config.js loaded, reinitializing API config`);
      initializeApiConfig();
      clearInterval(checkConfigInit);
    }
    // Stop checking after 2 seconds (100 x 20ms checks)
    if (initCheckCount > 100) {
      clearInterval(checkConfigInit);
    }
  }, 20);
}

// Simple health check state
let apiHealthy = true;
let lastHealthCheck = 0;
const HEALTH_CHECK_INTERVAL = 30000;

const _checkApiHealth = async () => {
  const now = Date.now();
  if (now - lastHealthCheck < HEALTH_CHECK_INTERVAL) {
    return apiHealthy;
  }

  try {
    const response = await fetch(`${currentConfig.baseURL}/api/health`, {
      method: "GET",
      signal: AbortSignal.timeout(3000),
    });
    apiHealthy = response?.ok;
    lastHealthCheck = now;
  } catch (error) {
    apiHealthy = false;
    lastHealthCheck = now;
  }

  return apiHealthy;
};

// Log config in development only (suppressed in production)
if (typeof window !== "undefined" && window.location?.hostname === "localhost") {
  if (!currentConfig.apiUrl || currentConfig.apiUrl === "") {
    console.debug(
      "[DEV] API using local proxy:",
      currentConfig.baseURL || "(relative path)"
    );
  }
}

// Create axios instance with dynamic baseURL resolution
// In production, wait up to 100ms for window.__CONFIG__ to load before initializing
let resolvedBaseURL = currentConfig.baseURL;

if (typeof window !== "undefined" && !currentConfig.baseURL && !import.meta.env?.DEV) {
  // In production with no baseURL yet, use window.__CONFIG__ directly if available
  resolvedBaseURL = window.__CONFIG__?.API_URL || currentConfig.baseURL;
}

let api = axios.create({
  baseURL: resolvedBaseURL,
  timeout: currentConfig.isServerless ? 45000 : 30000,
  headers: {
    "Content-Type": "application/json",
  },
});

// Token refresh management
let _refreshCallback = null;
let isRefreshing = false;
let failedQueue = [];

export const setRefreshCallback = (fn) => {
  _refreshCallback = fn;
};

const processQueue = (error, token = null) => {
  failedQueue.forEach((prom) =>
    error ? prom.reject(error) : prom.resolve(token)
  );
  failedQueue = [];
};

// Request interceptor - add auth token and track timing
try {
  if (api && api.interceptors) {
    api.interceptors.request.use(
      (config) => {
        config.metadata = { startTime: new Date() };
        const authHeader = tokenManager.getAuthHeader();
        if (authHeader) {
          config.headers.Authorization = authHeader.Authorization;
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    // Response interceptor - handle errors with retry logic
    api.interceptors.response.use(
      (response) => response,
      async (error) => {
        const originalRequest = error.config;

        // Handle 401 — try refresh once, then redirect
        if (error.response?.status === 401) {
          // Guard against infinite retry loops: only attempt refresh once per request
          if (originalRequest._retried) {
            tokenManager.clearTokens();
            if (typeof window !== "undefined" && window.location) {
              window.location.href = "/login";
            }
            return Promise.reject(error);
          }

          if (isRefreshing) {
            // Already refreshing, queue this request
            return new Promise((resolve, reject) => {
              failedQueue.push({ resolve, reject });
            })
              .then((token) => {
                originalRequest.headers.Authorization = `Bearer ${token}`;
                originalRequest._retried = true;
                return api(originalRequest);
              })
              .catch((err) => Promise.reject(err));
          }

          isRefreshing = true;
          originalRequest._retried = true;

          if (_refreshCallback) {
            try {
              const result = await _refreshCallback();
              if (result.success) {
                const newToken = tokenManager.getToken('access');
                processQueue(null, newToken);
                originalRequest.headers.Authorization = `Bearer ${newToken}`;
                isRefreshing = false;
                return api(originalRequest);
              }
            } catch (refreshError) {
              processQueue(refreshError, null);
              isRefreshing = false;
            }
          }

          isRefreshing = false;
          tokenManager.clearTokens();
          if (typeof window !== "undefined" && window.location) {
            window.location.href = "/login";
          }
        }

        // Handle 403 — permission denied
        if (error.response?.status === 403) {
          const forbiddenError = new Error("You do not have permission to perform this action.");
          forbiddenError.code = "FORBIDDEN";
          forbiddenError.status = 403;
          return Promise.reject(forbiddenError);
        }

        return Promise.reject(error);
      }
    );
  }
} catch (error) {
  console.warn("[API] Interceptor setup failed:", error.message);
}

// ============================================
// RESPONSE NORMALIZATION HELPERS
// ============================================
// Data extraction moved to canonical responseNormalizer.js
// Import from there if needed (currently only used by useApiQuery/useApiPaginatedQuery)

// ============================================
// ERROR HANDLING & CACHE HELPERS
// ============================================

// Helper to handle API errors with graceful degradation
const handleApiError = async (error, cacheKey, fallbackData, action = "fetch") => {
  const status = error.response?.status;
  const isNetworkError = !error.response;

  let errorMessage = error.message;
  if (status === 503) {
    errorMessage = "API temporarily unavailable. Showing cached data if available.";
  } else if (status === 429) {
    errorMessage = "Too many requests. Please try again later.";
  } else if (isNetworkError) {
    errorMessage = "Network error. Showing cached data if available.";
  }

  console.warn(`[API] Error during ${action} (${status || 'network'}):`, errorMessage);

  // Try to return cached data if available
  if (cacheKey) {
    const cached = await dataCache.get(cacheKey);
    if (cached) {
      console.debug(`[API] Using cached data for ${cacheKey}`);
      return { success: true, data: cached, fromCache: true, error: errorMessage };
    }
  }

  return { success: false, data: fallbackData, fromCache: false, error: errorMessage };
};

// ============================================
// MARKET DATA FUNCTIONS
// ============================================

export const getMarketTechnicals = async () => {
  try {
    const response = await api.get("/api/market/technicals");
    // Cache successful response
    if (response.data?.success !== false) {
      dataCache.set("market_technicals", response.data);
    }
    return response.data;
  } catch (error) {
    return handleApiError(error, "market_technicals", {}, "fetch market technicals");
  }
};

export const getMarketSentimentData = async (range = "1d") => {
  try {
    const response = await api.get(`/api/market/sentiment?range=${range}`);
    if (response.data?.success !== false) {
      dataCache.set("market_sentiment", response.data, { ttl: 10 * 60 * 1000 });
    }
    return response.data;
  } catch (error) {
    return handleApiError(error, "market_sentiment", { sentiment: 0.5 }, "fetch market sentiment");
  }
};

export const getMarketSeasonalityData = async () => {
  try {
    const response = await api.get("/api/market/seasonality");
    return response.data;
  } catch (error) {
    console.error("Error fetching market seasonality:", error);
    return { success: false, data: {}, error: error.message };
  }
};

export const getMarketCorrelation = async (symbols = null) => {
  try {
    const params = symbols ? `?symbols=${symbols}` : "";
    const response = await api.get(`/api/market/correlation${params}`);
    return response.data;
  } catch (error) {
    console.error("Error fetching market correlation:", error);
    return { success: false, data: {}, error: error.message };
  }
};

export const getMarketIndices = async () => {
  try {
    const response = await api.get("/api/market/indices");
    return response.data;
  } catch (error) {
    console.error("Error fetching market indices:", error);
    return { success: false, data: [], error: error.message };
  }
};

export const getMarketTopMovers = async () => {
  try {
    const response = await api.get("/api/market/top-movers");
    return response.data;
  } catch (error) {
    console.error("Error fetching market top movers:", error);
    return { success: false, data: [], error: error.message };
  }
};

export const getMarketCapDistribution = async () => {
  try {
    const response = await api.get("/api/market/cap-distribution");
    return response.data;
  } catch (error) {
    console.error("Error fetching market cap distribution:", error);
    return { success: false, data: [], error: error.message };
  }
};

// ============================================
// FINANCIAL DATA FUNCTIONS
// ============================================

export const getStocks = async (params = {}) => {
  try {
    const queryStr = new URLSearchParams(params).toString();
    const url = queryStr ? `/api/stocks?${queryStr}` : "/api/stocks";
    const response = await api.get(url);
    // Transform response format for consistency with frontend expectations
    // API returns { items: [...] }, but frontend expects { data: [...] }
    const transformedData = {
      ...response.data,
      data: (response.data.items || []).map(item => ({
        ...item,
        ticker: item.symbol, // Map symbol to ticker for compatibility
        short_name: item.security_name || item.name, // Use security_name from API or fallback to name
      })),
    };
    // Cache successful response
    if (transformedData.success !== false && transformedData.data?.length > 0) {
      dataCache.set("stocks", transformedData, { ttl: 5 * 60 * 1000 });
    }
    return transformedData;
  } catch (error) {
    const cached = await dataCache.get("stocks");
    if (cached) {
      console.debug("[API] Using cached stocks data due to error");
      return { success: true, data: cached.data || [], fromCache: true, error: error.message };
    }
    return handleApiError(error, null, [], "fetch stocks");
  }
};

export const getBalanceSheet = async (ticker, period = "annual") => {
  try {
    const response = await api.get(`/api/financials/${ticker}/balance-sheet?period=${period}`);
    return response.data;
  } catch (error) {
    console.error("Error fetching balance sheet:", error);
    return { success: false, data: {}, error: error.message };
  }
};

export const getIncomeStatement = async (ticker, period = "annual") => {
  try {
    const response = await api.get(`/api/financials/${ticker}/income-statement?period=${period}`);
    return response.data;
  } catch (error) {
    console.error("Error fetching income statement:", error);
    return { success: false, data: {}, error: error.message };
  }
};

export const getCashFlowStatement = async (ticker, period = "annual") => {
  try {
    const response = await api.get(`/api/financials/${ticker}/cash-flow?period=${period}`);
    return response.data;
  } catch (error) {
    console.error("Error fetching cash flow statement:", error);
    return { success: false, data: {}, error: error.message };
  }
};

export const getKeyMetrics = async (ticker) => {
  try {
    const response = await api.get(`/api/financials/${ticker}/key-metrics`);
    return response.data;
  } catch (error) {
    console.error("Error fetching key metrics:", error);
    return { success: false, data: {}, error: error.message };
  }
};

// ============================================
// CONTACT & MESSAGING FUNCTIONS
// ============================================

export const getContactSubmissions = async () => {
  try {
    const response = await api.get("/api/contact/submissions");
    return response.data;
  } catch (error) {
    console.error("Error fetching contact submissions:", error);
    return { success: false, data: { submissions: [], total: 0 }, error: error.message };
  }
};

export const submitContact = async (data) => {
  try {
    const response = await api.post("/api/contact", data);
    return response.data;
  } catch (error) {
    console.error("Error submitting contact form:", error);
    return { success: false, error: error.message };
  }
};

// ============================================
// USER SETTINGS FUNCTIONS
// ============================================

export const getSettings = async () => {
  try {
    const response = await api.get("/api/settings");
    return response.data;
  } catch (error) {
    console.error("Error fetching settings:", error);
    return { success: false, data: {}, error: error.message };
  }
};

export const updateSettings = async (settings) => {
  try {
    const response = await api.post("/api/settings", settings);
    return response.data;
  } catch (error) {
    console.error("Error updating settings:", error);
    return { success: false, error: error.message };
  }
};

// ============================================
// DIAGNOSTICS & ADMIN FUNCTIONS
// ============================================

export const getDiagnosticInfo = () => {
  try {
    return {
      apiUrl: currentConfig.apiUrl,
      baseURL: currentConfig.baseURL,
      isDev: currentConfig.isDev,
      isDevelopment: currentConfig.isDevelopment,
      isProduction: currentConfig.isProduction,
      isServerless: currentConfig.isServerless,
    };
  } catch (error) {
    console.error("Error getting diagnostic info:", error);
    return {};
  }
};

export const getCurrentBaseURL = () => {
  return currentConfig.baseURL || "/";
};

// ============================================
// HEALTH CHECK & TESTING FUNCTIONS
// ============================================

export const healthCheck = async () => {
  try {
    const response = await api.get("/api/health");
    return response.data;
  } catch (error) {
    console.error("Error fetching health check:", error);
    return { success: false, error: error.message };
  }
};

export const testApiConnection = async () => {
  try {
    const response = await api.get("/api/health");
    return response.data;
  } catch (error) {
    console.error("Error testing API connection:", error);
    return { success: false, error: error.message };
  }
};

// ============================================
// EXTERNAL DATA FUNCTIONS
// ============================================

export const getNaaimData = async () => {
  try {
    const response = await api.get("/api/market/naaim");
    return response.data;
  } catch (error) {
    console.error("Error fetching NAAIM data:", error);
    return { success: false, data: { sentiment: 0.5 }, error: error.message };
  }
};

export const getFearGreedData = async (range = "30d") => {
  try {
    const response = await api.get(`/api/market/fear-greed?range=${range}`);
    return response.data;
  } catch (error) {
    console.error("Error fetching Fear & Greed data:", error);
    return { success: false, data: { sentiment: 50 }, error: error.message };
  }
};

// Export the axios instance for direct use
export { api };
export default api;

