import axios from "axios";
import { tokenManager } from "./tokenManager";

// Get API configuration
export const getApiConfig = () => {
  // STRICT 3-LEVEL URL RESOLUTION - no hardcoded production URLs
  // 1. Runtime injection (AWS deployment)
  if (typeof window !== "undefined" && window.__CONFIG__?.API_URL) {
    const apiUrl = window.__CONFIG__.API_URL;
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

  return {
    baseURL: apiUrl,
    apiUrl: apiUrl,
    isServerless: false,
    isDev: isDev,
    isDevelopment: isDev,
    isProduction: false,
  };
};

// Create API instance that can be updated
let currentConfig = getApiConfig();

// DEBUG: Log the actual configuration being used
console.log('[API Config Debug]', {
  viteApiUrl: import.meta.env?.VITE_API_URL,
  isDev: import.meta.env?.DEV,
  currentConfig: currentConfig,
  windowConfig: typeof window !== "undefined" ? window.__CONFIG__?.API_URL : 'N/A'
});

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
    const response = await fetch(`${currentConfig.baseURL}/health`, {
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

// Log config in development only
if (typeof process === "undefined" || process.env.NODE_ENV !== "test") {
  if (!currentConfig.apiUrl || currentConfig.apiUrl === "" || currentConfig.apiUrl.includes("localhost")) {
    console.warn(
      "[API CONFIG] Using fallback API URL:",
      currentConfig.baseURL +
        "\nSet window.__CONFIG__.API_URL at runtime or VITE_API_URL at build time to override."
    );
  }
}

// Create axios instance
let api = axios.create({
  baseURL: currentConfig.baseURL,
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
          if (isRefreshing) {
            // Already refreshing, queue this request
            return new Promise((resolve, reject) => {
              failedQueue.push({ resolve, reject });
            })
              .then((token) => {
                originalRequest.headers.Authorization = `Bearer ${token}`;
                return api(originalRequest);
              })
              .catch((err) => Promise.reject(err));
          }

          isRefreshing = true;

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
// Standardize all API response handling across the app
// Instead of 14 different extraction patterns, use these 3 helpers

/**
 * Extract data from ANY API response format
 * Handles: items arrays, data objects, nested data.data, direct arrays
 */
export const extractData = (response) => {
  // Return the full data object with items and pagination intact
  // Pages expect: { items: [...], pagination: {...} }
  if (response?.data?.items) {
    return response.data;  // Return full response.data which includes items and pagination
  }
  // Handle double-nested responses
  if (response?.data?.data?.items) {
    return response.data.data;
  }
  if (Array.isArray(response?.data?.data)) {
    return { items: response.data.data, pagination: null };
  }
  // Handle direct array responses
  if (Array.isArray(response?.data)) {
    return { items: response.data, pagination: null };
  }
  // Handle object responses
  if (response?.data?.data) {
    return response.data.data;
  }
  // Fallback
  return response?.data || null;
};

/**
 * Extract pagination info from paginated responses
 */
export const extractPagination = (response) => {
  return response?.data?.pagination || response?.data?.data?.pagination || null;
};

/**
 * Check if response indicates success
 */
export const isResponseSuccess = (response) => {
  return response?.data?.success !== false && response?.status >= 200 && response?.status < 300;
};

/**
 * Backward compatibility - old name still works
 */
export const extractResponseData = extractData;

// ============================================
// MARKET DATA FUNCTIONS
// ============================================

export const getMarketTechnicals = async () => {
  try {
    const response = await api.get("/api/market/technicals");
    return response.data;
  } catch (error) {
    console.error("Error fetching market technicals:", error);
    return { success: false, data: {}, error: error.message };
  }
};

export const getMarketSentimentData = async (range = "1d") => {
  try {
    const response = await api.get(`/api/market/sentiment?range=${range}`);
    return response.data;
  } catch (error) {
    console.error("Error fetching market sentiment:", error);
    return { success: false, data: { sentiment: 0.5 }, error: error.message };
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
    return transformedData;
  } catch (error) {
    console.error("Error fetching stocks:", error);
    return { success: false, data: [], error: error.message };
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
    const response = await api.get("/api/test");
    return response.data;
  } catch (error) {
    console.error("Error testing API connection:", error);
    return { success: false, error: error.message };
  }
};

// ============================================
// EXTERNAL DATA FUNCTIONS
// ============================================

// Aliases for backward compatibility
export const getNaaimData = getMarketSentimentData;
export const getFearGreedData = getMarketSentimentData;

// Export the axios instance for direct use
export { api };
export default api;
