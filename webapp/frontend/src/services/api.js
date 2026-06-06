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

// Circuit breaker pattern to prevent cascading failures
const CircuitBreaker = {
  state: 'CLOSED', // CLOSED, OPEN, HALF_OPEN
  failureCount: 0,
  successCount: 0,
  lastFailureTime: 0,
  FAILURE_THRESHOLD: 15, // Open circuit after 15 failures (allows Lambda cold start + RDS recovery time)
  SUCCESS_THRESHOLD: 5, // Close circuit after 5 successes in half-open state
  RECOVERY_TIMEOUT: 120000, // 120 seconds (2 min) before attempting recovery - matches RDS restart time
};

const checkCircuitBreaker = () => {
  const now = Date.now();

  if (CircuitBreaker.state === 'OPEN') {
    // If enough time has passed, attempt recovery
    if (now - CircuitBreaker.lastFailureTime > CircuitBreaker.RECOVERY_TIMEOUT) {
      CircuitBreaker.state = 'HALF_OPEN';
      CircuitBreaker.successCount = 0;
      console.warn('[Circuit Breaker] Attempting recovery (HALF_OPEN state)');
    } else {
      // Still in failure window, reject immediately
      throw new Error('API service temporarily unavailable (circuit breaker OPEN). Retrying in a moment...');
    }
  }
};

const recordCircuitBreakerSuccess = () => {
  if (CircuitBreaker.state === 'HALF_OPEN') {
    CircuitBreaker.successCount++;
    if (CircuitBreaker.successCount >= CircuitBreaker.SUCCESS_THRESHOLD) {
      CircuitBreaker.state = 'CLOSED';
      CircuitBreaker.failureCount = 0;
      console.log('[Circuit Breaker] Recovered (CLOSED state)');
    }
  } else if (CircuitBreaker.state === 'CLOSED') {
    CircuitBreaker.failureCount = Math.max(0, CircuitBreaker.failureCount - 1);
  }
};

const recordCircuitBreakerFailure = () => {
  CircuitBreaker.lastFailureTime = Date.now();
  CircuitBreaker.failureCount++;

  if (CircuitBreaker.failureCount >= CircuitBreaker.FAILURE_THRESHOLD) {
    CircuitBreaker.state = 'OPEN';
    console.error(`[Circuit Breaker] Too many failures (${CircuitBreaker.failureCount}). Opening circuit.`);
  }
};

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
// In production, use currentConfig which already checks window.__CONFIG__ as fallback (line 14-20)
let api = axios.create({
  baseURL: currentConfig.baseURL,
  timeout: 35000, // Match Vite proxy timeout (30s Lambda + 5s buffer)
  headers: {
    "Content-Type": "application/json",
  },
});

// Update API baseURL after config.js loads (production) — re-check window.__CONFIG__
// This handles the case where config.js loads after axios is created
if (typeof window !== "undefined" && !import.meta.env?.DEV) {
  const configCheckInterval = setInterval(() => {
    const newConfig = getApiConfig();
    if (newConfig.baseURL && newConfig.baseURL !== api.defaults.baseURL) {
      api.defaults.baseURL = newConfig.baseURL;
      currentConfig = newConfig;
      console.info(`[API Config Updated] baseURL now set to: ${newConfig.baseURL}`);
      clearInterval(configCheckInterval);
    }
  }, 100);  // Check every 100ms
  // Wait up to 10 minutes (600000ms) for config.js to load before giving up
  // Accounts for slow production deployments and CloudFront CDN lag
  setTimeout(() => {
    clearInterval(configCheckInterval);
    if (!currentConfig.baseURL || currentConfig.baseURL === '') {
      console.error('[API Config] CRITICAL: Config.js never loaded after 10 minutes. API will not function without valid baseURL.');
    }
  }, 600000);  // 10 minutes timeout
}

// Token refresh management
let _refreshCallback = null;
let isRefreshing = false;
let failedQueue = [];
let lastTokenRefreshTime = 0;
const TOKEN_REFRESH_GRACE_PERIOD = 5000; // 5 second grace period before forcing logout

export const setRefreshCallback = (fn) => {
  _refreshCallback = fn;
};

const processQueue = (error, token = null) => {
  failedQueue.forEach((prom) =>
    error ? prom.reject(error) : prom.resolve(token)
  );
  failedQueue = [];
};

// Request interceptor - add auth token, track timing, and check circuit breaker
try {
  if (api && api.interceptors) {
    api.interceptors.request.use(
      (config) => {
        // Check circuit breaker before allowing request
        try {
          checkCircuitBreaker();
        } catch (cbError) {
          // Circuit breaker is OPEN, reject request immediately
          return Promise.reject(cbError);
        }

        config.metadata = { startTime: new Date() };
        const authHeader = tokenManager.getAuthHeader();
        if (authHeader) {
          config.headers.Authorization = authHeader.Authorization;
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    // Response interceptor - handle errors with retry logic and circuit breaker
    api.interceptors.response.use(
      (response) => {
        // Record success for circuit breaker recovery
        recordCircuitBreakerSuccess();
        return response;
      },
      async (error) => {
        const originalRequest = error.config;

        // Record failure for circuit breaker
        const status = error.response?.status;
        if (!originalRequest || !originalRequest._cbRecorded) {
          // Only record once per request
          if (status >= 500 || (status === 429 && CircuitBreaker.state === 'CLOSED')) {
            recordCircuitBreakerFailure();
          }
          if (originalRequest) {
            originalRequest._cbRecorded = true;
          }
        }

        // Handle 401 — try refresh with grace period, allow multiple retries within grace period
        if (error.response?.status === 401) {
          const now = Date.now();
          const timeSinceLastRefresh = now - lastTokenRefreshTime;

          // Guard against infinite retry loops: only attempt refresh if within grace period
          if (timeSinceLastRefresh > TOKEN_REFRESH_GRACE_PERIOD && originalRequest._retried) {
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
          lastTokenRefreshTime = now;

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
              // After failed refresh, if still within grace period, allow user to retry
              // Otherwise force logout
              if (now - lastTokenRefreshTime > TOKEN_REFRESH_GRACE_PERIOD) {
                tokenManager.clearTokens();
                if (typeof window !== "undefined" && window.location) {
                  window.location.href = "/login";
                }
              }
              return Promise.reject(refreshError);
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

