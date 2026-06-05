import axios from "axios";
import { tokenManager } from "./tokenManager";
import dataCache from "./dataCache";
import { extractData } from "../utils/responseNormalizer";

// Get API configuration with explicit fallback chain
// Order: (1) Runtime injection → (2) Build-time env var → (3) Dev proxy
export const getApiConfig = () => {
  const isDev = import.meta.env?.DEV;
  let apiUrl = "";
  let source = "fallback";

  // Level 1: Runtime injection (from config.js in production)
  if (typeof window !== "undefined" && window.__CONFIG__ && 'API_URL' in window.__CONFIG__) {
    apiUrl = window.__CONFIG__.API_URL;
    source = "window.__CONFIG__";
    if (!apiUrl && isDev) {
      source = "window.__CONFIG__ (empty for Vite proxy)";
    }
  }
  // Level 2: Build-time environment variable (from CI/CD)
  else if (import.meta.env?.VITE_API_URL) {
    apiUrl = import.meta.env.VITE_API_URL;
    source = "VITE_API_URL env var";
  }
  // Level 3: Development fallback (relative path with Vite proxy)
  else {
    apiUrl = "";
    source = isDev ? "Vite proxy (dev mode)" : "ERROR: No API URL configured";
  }

  const config = {
    baseURL: apiUrl,
    apiUrl: apiUrl,
    isServerless: !!(apiUrl && !apiUrl.includes("localhost")),
    isDev: isDev,
    isDevelopment: isDev,
    isProduction: !isDev,
    _source: source, // For debugging
  };

  // Log API configuration (helpful for debugging)
  if (typeof window !== "undefined" && window.location?.hostname === "localhost") {
    console.debug(`[API Config] Source: ${source}, baseURL: "${apiUrl || '(relative path)'}"`);
  }

  // Error tracking if API URL is not available in production
  if (!config.baseURL && !isDev) {
    const errorMsg = '[API CONFIG ERROR] No API URL available. The backend API is not configured. ' +
      'Check: (1) window.__CONFIG__.API_URL via config.js, (2) VITE_API_URL env var, or (3) network connectivity. ' +
      'The application will not function without a valid API endpoint.';
    console.error(errorMsg);
    config._configError = errorMsg;
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

// Note: Config loading is handled by main.jsx which waits for config.js to load
// before rendering the app. No need for redundant polling here.

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
      // Ensure cached data has consistent envelope format
      // Cache stores normalized data from successful responses
      return {
        statusCode: 200,
        ...cached,
        fromCache: true,
        error: errorMessage,
      };
    }
  }

  return { statusCode: 400, ...fallbackData, fromCache: false, error: errorMessage };
};

// ============================================
// MARKET DATA FUNCTIONS
// ============================================

export const getMarketTechnicals = async () => {
  try {
    const response = await api.get("/api/market/technicals");
    // Normalize response envelope for consistent structure
    const normalized = extractData(response);
    // Cache normalized data
    if (normalized && normalized.statusCode !== 400) {
      dataCache.set("market_technicals", normalized);
    }
    return normalized;
  } catch (error) {
    return handleApiError(error, "market_technicals", { data: {} }, "fetch market technicals");
  }
};

export const getMarketSentimentData = async (range = "1d") => {
  try {
    const response = await api.get(`/api/market/sentiment?range=${range}`);
    const normalized = extractData(response);
    if (normalized && normalized.statusCode !== 400) {
      dataCache.set("market_sentiment", normalized, { ttl: 10 * 60 * 1000 });
    }
    return normalized;
  } catch (error) {
    return handleApiError(error, "market_sentiment", { data: { sentiment: 0.5 } }, "fetch market sentiment");
  }
};

export const getMarketSeasonalityData = async () => {
  try {
    const response = await api.get("/api/market/seasonality");
    return extractData(response);
  } catch (error) {
    console.error("Error fetching market seasonality:", error);
    return { statusCode: 400, data: {}, error: error.message };
  }
};

export const getMarketCorrelation = async (symbols = null) => {
  try {
    const params = symbols ? `?symbols=${symbols}` : "";
    const response = await api.get(`/api/market/correlation${params}`);
    return extractData(response);
  } catch (error) {
    console.error("Error fetching market correlation:", error);
    return { statusCode: 400, data: {}, error: error.message };
  }
};

export const getMarketIndices = async () => {
  try {
    const response = await api.get("/api/market/indices");
    return extractData(response);
  } catch (error) {
    console.error("Error fetching market indices:", error);
    return { statusCode: 400, items: [], error: error.message };
  }
};

export const getMarketTopMovers = async () => {
  try {
    const response = await api.get("/api/market/top-movers");
    return extractData(response);
  } catch (error) {
    console.error("Error fetching market top movers:", error);
    return { statusCode: 400, items: [], error: error.message };
  }
};

export const getMarketCapDistribution = async () => {
  try {
    const response = await api.get("/api/market/cap-distribution");
    return extractData(response);
  } catch (error) {
    console.error("Error fetching market cap distribution:", error);
    return { statusCode: 400, items: [], error: error.message };
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
    // Normalize response envelope to consistent structure
    const normalized = extractData(response);

    // Transform items: map symbol→ticker, apply company_name alias fallback
    // responseNormalizer provides items array (filtered of null/undefined)
    const transformedData = {
      ...normalized,
      items: (normalized.items || []).map(item => ({
        ...item,
        ticker: item.symbol || '',
        short_name: item.company_name || item.security_name || item.name || '',
      })),
    };

    // Cache normalized, transformed data
    if (transformedData.items?.length > 0) {
      dataCache.set("stocks", transformedData, { ttl: 5 * 60 * 1000 });
    }
    return transformedData;
  } catch (error) {
    const cached = await dataCache.get("stocks");
    if (cached) {
      console.debug("[API] Using cached stocks data due to error");
      return { statusCode: 200, ...cached, fromCache: true, error: error.message };
    }
    return handleApiError(error, null, { items: [] }, "fetch stocks");
  }
};

export const getBalanceSheet = async (ticker, period = "annual") => {
  try {
    const response = await api.get(`/api/financials/${ticker}/balance-sheet?period=${period}`);
    return extractData(response);
  } catch (error) {
    console.error("Error fetching balance sheet:", error);
    return { statusCode: 400, data: {}, error: error.message };
  }
};

export const getIncomeStatement = async (ticker, period = "annual") => {
  try {
    const response = await api.get(`/api/financials/${ticker}/income-statement?period=${period}`);
    return extractData(response);
  } catch (error) {
    console.error("Error fetching income statement:", error);
    return { statusCode: 400, data: {}, error: error.message };
  }
};

export const getCashFlowStatement = async (ticker, period = "annual") => {
  try {
    const response = await api.get(`/api/financials/${ticker}/cash-flow?period=${period}`);
    return extractData(response);
  } catch (error) {
    console.error("Error fetching cash flow statement:", error);
    return { statusCode: 400, data: {}, error: error.message };
  }
};

export const getKeyMetrics = async (ticker) => {
  try {
    const response = await api.get(`/api/financials/${ticker}/key-metrics`);
    return extractData(response);
  } catch (error) {
    console.error("Error fetching key metrics:", error);
    return { statusCode: 400, data: {}, error: error.message };
  }
};

// ============================================
// CONTACT & MESSAGING FUNCTIONS
// ============================================

export const getContactSubmissions = async () => {
  try {
    const response = await api.get("/api/contact/submissions");
    return extractData(response);
  } catch (error) {
    console.error("Error fetching contact submissions:", error);
    return { statusCode: 400, data: { submissions: [], total: 0 }, error: error.message };
  }
};

export const submitContact = async (data) => {
  try {
    const response = await api.post("/api/contact", data);
    return extractData(response);
  } catch (error) {
    console.error("Error submitting contact form:", error);
    return { statusCode: 400, error: error.message };
  }
};

// ============================================
// USER SETTINGS FUNCTIONS
// ============================================

export const getSettings = async () => {
  try {
    const response = await api.get("/api/settings");
    return extractData(response);
  } catch (error) {
    console.error("Error fetching settings:", error);
    return { statusCode: 400, data: {}, error: error.message };
  }
};

export const updateSettings = async (settings) => {
  try {
    const response = await api.post("/api/settings", settings);
    return extractData(response);
  } catch (error) {
    console.error("Error updating settings:", error);
    return { statusCode: 400, error: error.message };
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
      configSource: currentConfig._source || 'unknown',
      configError: currentConfig._configError || null,
    };
  } catch (error) {
    console.error("Error getting diagnostic info:", error);
    return {};
  }
};

// Check if API is properly configured for making requests
export const isApiConfigured = () => {
  return !!(currentConfig.baseURL || currentConfig.isDev);
};

// Get a user-friendly error message if API is not configured
export const getApiConfigError = () => {
  if (!isApiConfigured() && !currentConfig.isDev) {
    return 'API Backend is not configured. Please check the server configuration or contact support.';
  }
  return null;
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
    return extractData(response);
  } catch (error) {
    console.error("Error fetching health check:", error);
    return { statusCode: 400, error: error.message };
  }
};

export const testApiConnection = async () => {
  try {
    const response = await api.get("/api/health");
    return extractData(response);
  } catch (error) {
    console.error("Error testing API connection:", error);
    return { statusCode: 400, error: error.message };
  }
};

// ============================================
// EXTERNAL DATA FUNCTIONS
// ============================================

export const getNaaimData = async () => {
  try {
    const response = await api.get("/api/market/naaim");
    return extractData(response);
  } catch (error) {
    console.error("Error fetching NAAIM data:", error);
    return { statusCode: 400, data: { sentiment: 0.5 }, error: error.message };
  }
};

export const getFearGreedData = async (range = "30d") => {
  try {
    const response = await api.get(`/api/market/fear-greed?range=${range}`);
    return extractData(response);
  } catch (error) {
    console.error("Error fetching Fear & Greed data:", error);
    return { statusCode: 400, data: { sentiment: 50 }, error: error.message };
  }
};

// Export the axios instance for direct use
export { api };
export default api;

