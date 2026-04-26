import axios from "axios";

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
  const apiUrl = "/";

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
  if (!currentConfig.apiUrl || currentConfig.apiUrl.includes("localhost")) {
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

// Request interceptor - add auth token and track timing
try {
  if (api && api.interceptors) {
    api.interceptors.request.use(
      (config) => {
        config.metadata = { startTime: new Date() };
        if (typeof window !== "undefined") {
          const token = localStorage.getItem("authToken") || localStorage.getItem("accessToken");
          if (token) {
            config.headers.Authorization = `Bearer ${token}`;
          }
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    // Response interceptor - handle errors
    api.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response?.status === 401) {
          localStorage.removeItem("authToken");
          localStorage.removeItem("accessToken");
          if (typeof window !== "undefined" && window.location) {
            window.location.href = "/login";
          }
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
        short_name: item.name, // Map name to short_name for compatibility
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
    const response = await api.get(`/api/stocks/${ticker}`);
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

export const getNaaimData = async () => {
  try {
    const response = await api.get("/api/market/sentiment");
    return response.data;
  } catch (error) {
    console.error("Error fetching NAAIM data:", error);
    return { success: false, data: {}, error: error.message };
  }
};

export const getFearGreedData = async () => {
  try {
    const response = await api.get("/api/market/sentiment");
    return response.data;
  } catch (error) {
    console.error("Error fetching Fear/Greed data:", error);
    return { success: false, data: {}, error: error.message };
  }
};

// Export the axios instance for direct use
export { api };
export default api;
