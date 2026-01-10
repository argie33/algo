import axios from "axios";

// Get API configuration
export const getApiConfig = () => {
  // Dynamic API URL resolution: runtime > build-time > infer from location > fallback
  let runtimeApiUrl =
    typeof window !== "undefined" &&
    window.__CONFIG__ &&
    window.__CONFIG__.API_URL
      ? window.__CONFIG__.API_URL
      : null;

  let apiUrl = runtimeApiUrl || (import.meta.env && import.meta.env.VITE_API_URL);

  // In development mode, use relative paths so Vite proxy handles it
  const isDev = import.meta.env && import.meta.env.DEV;

  if (!apiUrl && isDev) {
    // Use relative path in development - Vite proxy will forward to localhost:3001
    apiUrl = "/";
  } else if (!apiUrl && typeof window !== "undefined") {
    const { hostname, origin, port, protocol } = window.location;
    if (hostname === "localhost" || hostname === "127.0.0.1") {
      apiUrl = "http://localhost:3001";
    } else {
      // AWS production - use Lambda API Gateway endpoint
      // Default to AWS Lambda endpoint for serverless API
      apiUrl = "https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev";
    }
  }

  // Final fallback (shouldn't reach here)
  if (!apiUrl) {
    apiUrl = "/";
  }

  // Only log in development, not in tests
  if (typeof process === "undefined" || process.env.NODE_ENV !== "test") {
    console.log("🔧 [API CONFIG] URL Resolution:", {
      runtimeApiUrl,
      envApiUrl: import.meta.env && import.meta.env.VITE_API_URL,
      finalApiUrl: apiUrl,
      windowConfig:
        typeof window !== "undefined" ? window.__CONFIG__ : "undefined",
      allEnvVars: import.meta.env || {},
    });
  }

  // Detect environment properly for both runtime and test contexts
  const isTestEnv =
    typeof process !== "undefined" && process.env.NODE_ENV === "test";
  const environment = isTestEnv
    ? "test"
    : (import.meta.env && import.meta.env.MODE) || "development";
  const isDevelopment = isTestEnv
    ? true
    : !!(import.meta.env && import.meta.env.DEV);
  const isProduction = isTestEnv
    ? false
    : !!(import.meta.env && import.meta.env.PROD);

  return {
    baseURL: apiUrl,
    isServerless: !!apiUrl && !apiUrl.includes("localhost"),
    apiUrl: apiUrl,
    isConfigured: !!apiUrl && !apiUrl.includes("localhost"),
    environment: environment,
    isDevelopment: isDevelopment,
    isProduction: isProduction,
    baseUrl: import.meta.env && import.meta.env.BASE_URL,
    allEnvVars: import.meta.env || {},
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
      method: "GET",
      timeout: 3000,
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

// Warn if API URL is fallback (localhost) - skip in tests
if (typeof process === "undefined" || process.env.NODE_ENV !== "test") {
  if (!currentConfig.apiUrl || currentConfig.apiUrl.includes("localhost")) {
    console.warn(
      "[API CONFIG] Using fallback API URL:",
      currentConfig.baseURL +
        "\nSet window.__CONFIG__.API_URL at runtime or VITE_API_URL at build time to override."
    );
  }
}

// Create API instance - test-safe
// IMPORTANT: Always use absolute URL to backend for reliable proxying
let api = axios.create({
  baseURL: currentConfig.baseURL, // Always use absolute URL to backend (http://localhost:3001 or production URL)
  timeout: currentConfig.isServerless ? 45000 : 30000, // Longer timeout for Lambda cold starts
  headers: {
    "Content-Type": "application/json",
    Authorization: "Bearer dev-bypass-token", // Development authentication
  },
});

// Add request interceptor to track ongoing requests - test-safe
try {
  if (api && api.interceptors) {
    api.interceptors.request.use(
      (config) => {
        // Add timestamp for request duration tracking
        config.metadata = { startTime: new Date() };
        return config;
      },
      (error) => {
        return Promise.reject(error);
      }
    );
  }
} catch (error) {
  // Ignore interceptor errors in test environment
  if (typeof process !== "undefined" && process.env.NODE_ENV === "test") {
    console.warn("[API] Interceptor setup skipped in test environment");
  }
}

// Add response interceptor for better error handling - test-safe
try {
  if (api && api.interceptors) {
    api.interceptors.response.use(
      (response) => {
        // Track request duration for performance monitoring
        if (response.config.metadata) {
          const duration = new Date() - response.config.metadata.startTime;
          if (duration > 10000) {
            // Log slow requests (>10s)
            console.warn(`⚠️ Slow API request detected:`, {
              url: response.config.url,
              method: response.config.method,
              duration: `${duration}ms`,
            });
          }
        }
        return response;
      },
      (error) => {
        // Enhanced error handling with user-friendly messages
        let userMessage = "An unexpected error occurred";

        if (error.code === "ECONNABORTED") {
          userMessage =
            "Request timed out. The server may be experiencing high load. Please try again.";
        } else if (error.code === "ERR_NETWORK") {
          userMessage =
            "Network connection failed. Please check your internet connection.";
        } else if (error.code === "ENOTFOUND") {
          userMessage = "Server could not be reached. Please try again later.";
        } else if (error.code === "CERT_UNTRUSTED") {
          userMessage = "Security certificate error. Please contact support.";
        } else if (error.response?.status === 401) {
          userMessage = "Authentication failed. Please sign in again.";
        } else if (error.response?.status === 403) {
          userMessage =
            "Access denied. You do not have permission for this resource.";
        } else if (error.response?.status === 404) {
          userMessage =
            "The requested resource was not found. Please check your request and try again.";
        } else if (error.response?.status === 429) {
          userMessage =
            "Too many requests. Please wait a moment and try again.";
        } else if (error.response?.status === 500) {
          userMessage =
            "Server error occurred. Our team has been notified. Please try again later.";
        } else if (error.response?.status === 502) {
          userMessage =
            "Bad gateway error. The service may be temporarily unavailable.";
        } else if (error.response?.status === 503) {
          userMessage =
            "Service temporarily unavailable. Please try again in a few minutes.";
        } else if (!navigator.onLine) {
          userMessage =
            "No internet connection. Please check your network and try again.";
        }

        // Add user-friendly message to error object
        error.userMessage = userMessage;

        // Enhanced error logging with more context
        const logData = {
          url: error.config?.url,
          method: error.config?.method,
          status: error.response?.status,
          statusText: error.response?.statusText,
          message: error.message,
          code: error.code,
          userMessage,
          stack: error.stack?.split("\n")[0], // Just first line of stack
        };

        // Log different error types with appropriate console methods
        if (error.response?.status >= 500) {
          console.error("❌ Server Error:", logData);
        } else if (error.response?.status >= 400) {
          console.warn("⚠️ Client Error:", logData);
        } else if (error.code) {
          console.error("❌ Network Error:", logData);
        } else {
          console.error("❌ Unknown Error:", logData);
        }

        return Promise.reject(error);
      }
    );
  }
} catch (error) {
  // Ignore interceptor errors in test environment
  if (typeof process !== "undefined" && process.env.NODE_ENV === "test") {
    console.warn(
      "[API] Response interceptor setup skipped in test environment"
    );
  }
}

// Export the api instance for direct use
export { api };

// Helper function to standardize API response parsing
// Handles various response formats: {data: ...}, {items: ...}, {history: ...}, raw array, etc.
export const extractDataFromResponse = (response, fallbackArray = []) => {
  if (!response) return fallbackArray;

  const data = response.data || response;

  // Try to extract array-like data in order of precedence
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.data)) return data.data;
  if (Array.isArray(data?.items)) return data.items;
  if (Array.isArray(data?.history)) return data.history;
  if (Array.isArray(data?.stocks)) return data.stocks;
  if (Array.isArray(data?.rows)) return data.rows;
  if (Array.isArray(data?.results)) return data.results;

  // If no array found, return fallback
  return fallbackArray;
};

// Alias for tests - saveApiKey is equivalent to addApiKey
export const saveApiKey = async (apiKeyData) => {
  try {
    const response = await api.post("/api/portfolio/api-keys", apiKeyData);
    const responseData = extractResponseData(response);
    return {
      data: responseData || null,
      success: true
    };
  } catch (error) {
    console.error("❌ Save API key error:", error);
    return {
      data: null,
      success: false,
      error: error?.response?.data?.error || error?.message || 'Failed to save API key'
    };
  }
};

// Test API key functionality
export const testApiKey = async (apiKeyData) => {
  try {
    const response = await api.post("/api/portfolio/test-api-key", apiKeyData);
    const responseData = extractResponseData(response);
    const isValid = responseData?.isValid ?? response?.data?.isValid ?? false;
    return {
      data: responseData || null,
      success: true,
      isValid
    };
  } catch (error) {
    console.error("❌ Test API key error:", error);
    return {
      data: null,
      success: false,
      isValid: false,
      error: error?.response?.data?.error || error?.message || 'Failed to test API key'
    };
  }
};

// User settings functions
export const getSettings = async () => {
  try {
    const response = await api.get("/api/user/settings");
    const responseData = extractResponseData(response);
    return {
      data: responseData || null,
      success: true
    };
  } catch (error) {
    console.error("❌ Get settings error:", error);
    return {
      data: null,
      success: false,
      error: error?.response?.data?.error || error?.message || 'Failed to fetch settings'
    };
  }
};

export const updateSettings = async (settings) => {
  try {
    const response = await api.put("/api/user/settings", settings);
    const responseData = extractResponseData(response);
    return {
      data: responseData || null,
      success: true
    };
  } catch (error) {
    console.error("❌ Update settings error:", error);
    return {
      data: null,
      success: false,
      error: error?.response?.data?.error || error?.message || 'Failed to update settings'
    };
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

// Request interceptor for logging and Lambda optimization - test-safe
try {
  api.interceptors.request.use(
    (config) => {
      // DEVELOPMENT MODE: Only block API calls if no API server is configured
      const isDevelopment =
        window.location.hostname === "localhost" ||
        window.location.hostname === "127.0.0.1" ||
        window.location.port === "5173";

      // Only block API calls in development if we don't have a configured API server
      const hasValidApiServer =
        currentConfig &&
        currentConfig.baseURL &&
        (currentConfig.baseURL.startsWith("http://localhost:") ||
          currentConfig.baseURL.startsWith("https://"));

      if (isDevelopment && !hasValidApiServer) {
        console.log("🚫 [API] Blocking API call - no server configured:", {
          baseURL: currentConfig.baseURL,
          hasValidApiServer,
        });
        const error = new Error("API calls disabled - no server configured");
        error.code = "NO_SERVER_CONFIGURED";
        return Promise.reject(error);
      }

      console.log("✅ [API] Allowing API call:", {
        isDevelopment,
        hasValidApiServer,
        baseURL: currentConfig.baseURL,
        url: config.url,
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
        if (
          import.meta.env.DEV &&
          (currentConfig.baseURL.includes("localhost:3001") ||
            import.meta.env.VITE_FORCE_DEV_AUTH === "true")
        ) {
          // If we have a dev token from devAuth service, replace it with bypass token
          if (!authToken || (authToken && authToken.startsWith("dev-"))) {
            console.log(
              "🔧 Development mode: Using dev-bypass-token for API calls"
            );
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
        message: error?.message || "Unknown error",
        status: error.response?.status,
        statusText: error.response?.statusText,
      });
      return Promise.reject(error);
    }
  );
} catch (error) {
  // Ignore interceptor errors in test environment
  if (typeof process !== "undefined" && process.env.NODE_ENV === "test") {
    console.warn("[API] Request interceptor setup skipped in test environment");
  }
}

// Enhanced diagnostics: Use our robust error logging system - test-safe
try {
  api.interceptors.response.use(
    (response) => {
      const fullUrl = `${response.config.baseURL || api.defaults.baseURL}${response.config.url}`;
      console.log(
        "[API SUCCESS]",
        response.config.method?.toUpperCase(),
        fullUrl,
        {
          status: response?.status,
          statusText: response?.statusText,
          dataSize: response?.data
            ? Array.isArray(response?.data)
              ? response.data?.length || 0
              : Object.keys(response?.data).length
            : 0,
        }
      );
      return response;
    },
    async (error) => {
      // Suppress all error logging in development mode to avoid console spam
      // Components should handle API errors gracefully with fallback data

      // Especially suppress development mode blocked requests
      if (error?.code === "DEV_MODE_BLOCKED") {
        return Promise.reject(error);
      }

      return Promise.reject(error);
    }
  );
} catch (error) {
  // Ignore interceptor errors in test environment
  if (typeof process !== "undefined" && process.env.NODE_ENV === "test") {
    console.warn(
      "[API] Response interceptor (diagnostics) setup skipped in test environment"
    );
  }
}

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

// Helper function to normalize API responses per RULES.md standardized format
// Handles multiple response patterns:
// 1. {data: {...}, success: true} → returns data object
// 2. {items: [...], pagination: {...}, success: true} → returns {items, pagination}
// 3. {success: true} → returns response.data
function normalizeResponse(response, expectArray = false) {
  if (!response || response.data === undefined) {
    return expectArray ? [] : null;
  }

  const data = response.data;

  // If response has 'items' and 'pagination', return as-is (already normalized)
  if (data && typeof data === 'object') {
    if (data.items && data.pagination) {
      return data; // Already has items/pagination structure
    }
    // If it has 'data' field, extract it (for {data: {...}, success: true} format)
    if (data.data !== undefined && data.success !== undefined) {
      return data.data;
    }
  }

  // Otherwise return data as-is
  return data;
}

// Helper to safely extract data from API response, handling all RULES.md formats
function extractResponseData(response) {
  if (!response || !response.data) return null;
  const data = response.data;

  // Paginated list response: {items: [...], pagination: {...}, success: true}
  if (data.items !== undefined && data.pagination !== undefined) {
    return { items: data.items, pagination: data.pagination };
  }

  // Nested data response: {data: {...}, success: true}
  if (data.data !== undefined && data.success !== undefined) {
    return data.data;
  }

  // Direct data response: {..., success: true}
  if (data.success !== undefined) {
    return data;
  }

  // Fallback: return data as-is
  return data;
}

// NOTE: Removed duplicate normalizeApiResponse - using exported version from top of file

// Keep this function for internal use if needed (not exported)
function normalizeApiResponseOld(response, expectArray = true) {
  console.log("🔍 normalizeApiResponse input:", {
    hasResponse: !!response,
    responseType: typeof response,
    hasData: !!(response && response?.data !== undefined),
    dataType: response?.data ? typeof response?.data : "undefined",
    isArray: Array.isArray(response?.data),
    expectArray,
  });

  // Handle axios response wrapper first
  if (response && response?.data !== undefined) {
    // Check if axios wrapped data
    const potentialData = response.data;
    // Only extract if the inner data is not another wrapper
    if (
      typeof potentialData === "object" &&
      (potentialData?.success !== undefined || Array.isArray(potentialData))
    ) {
      response = potentialData;
    }
  }

  // Handle backend API response format
  if (response && typeof response === "object") {
    // If response has 'success' property, check if it's successful
    if (response?.success === false) {
      console.error("❌ API request failed:", response?.error);
      return null;
    }

    // If response contains an error, return null
    if (response?.error) {
      console.error("❌ API error:", response?.error);
      return null;
    }

    // If response has a 'data' property AND it's not already extracted, use that
    if (response?.data !== undefined && typeof response.data === "object") {
      response = response.data;
    }
  }

  // Ensure we return an array if expected
  if (expectArray && !Array.isArray(response)) {
    if (response && typeof response === "object") {
      // Try to extract array from common response structures
      if (Array.isArray(response?.data)) {
        response = response?.data;
      } else if (Array.isArray(response?.items)) {
        response = response?.items;
      } else if (Array.isArray(response?.results)) {
        response = response?.results;
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
    length: Array.isArray(response) ? response?.length || 0 : "N/A",
    sample:
      Array.isArray(response) && response.length > 0 ? response[0] : response,
  });
  return response;
}

// --- PATCH: Log API config at startup ---
console.log("🚀 [API STARTUP] Initializing API configuration...");
console.log("🔧 [API CONFIG]", getApiConfig());
console.log(
  "📡 [AXIOS DEFAULT BASE URL]",
  api?.defaults?.baseURL || "undefined"
);

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
    const response = await api.get("/api/market/overview");
    console.log("📈 [API] Market overview raw response:", response);
    // Return { data: ... } structure for consistency
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    console.log("📈 [API] Market overview normalized result:", result);
    return result;
  } catch (error) {
    // Use console.warn for expected errors (503 = backend offline), console.error for unexpected
    const isExpectedError =
      error.response?.status === 503 ||
      error.response?.status === 502 ||
      error.message === "Network Error" ||
      error.code === "ERR_NETWORK";
    const logLevel = isExpectedError ? "warn" : "error";
    const logPrefix = isExpectedError
      ? "⚠️ [API] Market overview unavailable"
      : "❌ [API] Market overview error";

    console[logLevel](`${logPrefix}:`, error?.message || "Unknown error");

    // Only log full details for unexpected errors
    if (!isExpectedError) {
      console.error("Full error details:", {
        status: error.response?.status,
        statusText: error.response?.statusText,
        url: error.config?.url,
        method: error.config?.method,
      });
    }

    return { data: null };
  }
};

export const getTopStocks = async (params = {}) => {
  console.log("📈 [API] Fetching top stocks...", params);
  console.log("📈 [API] Current config:", getApiConfig());

  try {
    const queryParams = new URLSearchParams({
      limit: params.limit || 10,
      sortBy: params.sortBy || "composite_score",
      sortOrder: params.sortOrder || "desc",
      ...params,
    }).toString();

    // Use the new dedicated stock scores endpoint
    const endpoints = [`/api/scores/stockscores?${queryParams}`];
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
      const isExpectedError =
        lastError?.message === "Network Error" ||
        lastError?.code === "ERR_NETWORK" ||
        lastError?.response?.status === 503;
      if (isExpectedError) {
        console.warn(
          "⚠️ [API] Top stocks endpoints unavailable:",
          lastError?.message || "Unknown error"
        );
      } else {
        console.error("📈 [API] All top stocks endpoints failed:", lastError);
      }
      throw lastError;
    }

    console.log("📈 [API] Top stocks raw response:", response);
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    console.log("📈 [API] Top stocks normalized result:", result);
    return result;
  } catch (error) {
    // Use console.warn for expected errors (503 = backend offline), console.error for unexpected
    const isExpectedError =
      error.response?.status === 503 ||
      error.response?.status === 502 ||
      error.message === "Network Error" ||
      error.code === "ERR_NETWORK";
    const logLevel = isExpectedError ? "warn" : "error";
    const logPrefix = isExpectedError
      ? "⚠️ [API] Top stocks unavailable"
      : "❌ [API] Top stocks error";

    console[logLevel](`${logPrefix}:`, error?.message || "Unknown error");

    // Only log full details for unexpected errors
    if (!isExpectedError) {
      console.error("Full error details:", {
        status: error.response?.status,
        statusText: error.response?.statusText,
        url: error.config?.url,
        method: error.config?.method,
      });
    }
    return { data: null };
  }
};

export const getStockScores = async (symbol, params = {}) => {
  console.log(`📈 [API] Fetching scores for ${symbol}...`, params);
  console.log("📈 [API] Current config:", getApiConfig());

  try {
    const queryParams = new URLSearchParams({
      search: symbol,
      limit: 1,
      ...params,
    }).toString();

    const endpoint = `/api/scores/stockscores?${queryParams}`;

    console.log(`📈 [API] Trying scores endpoint: ${endpoint}`);
    const response = await api.get(endpoint);
    console.log(`📈 [API] SUCCESS with scores endpoint: ${endpoint}`, response?.data);

    // Backend returns: { success, items: [...], pagination: {...} }
    // Extract the first stock from items array
    const stocks = response?.data?.items ?? response?.data?.data ?? [];
    const stockData = stocks.length > 0 ? stocks[0] : null;

    if (!stockData) {
      console.warn(`⚠️ [API] No stock data found for ${symbol}`);
      return { data: null, success: false };
    }

    // Return properly formatted response - MUST wrap in { data: ... } per RULES.md
    return { data: stockData, success: true };
  } catch (error) {
    console.error(`❌ [API] Error fetching scores for ${symbol}:`, error.message);

    const isExpectedError =
      error?.message === "Network Error" ||
      error?.code === "ERR_NETWORK" ||
      error?.response?.status === 503;

    if (!isExpectedError) {
      console.error("Full error details:", {
        status: error.response?.status,
        statusText: error.response?.statusText,
        url: error.config?.url,
        method: error.config?.method,
      });
    }
    return { data: null };
  }
};

export const getMarketSentimentHistory = async (days = 30) => {
  console.log(`📊 [API] Fetching market sentiment history for ${days} days...`);

  try {
    const response = await api.get(
      `/api/sentiment/history?days=${days}`
    );
    console.log(`📊 [API] Fetched sentiment history:`, response.data);

    // Always return { data: ... } structure for consistency
    if (response?.data && typeof response?.data === "object") {
      console.log(
        "📊 [API] Returning sentiment data structure:",
        response?.data
      );
      return response?.data; // Backend already returns { data: ..., metadata: ... }
    }

    // Fallback to normalized response
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    console.log("📊 [API] Sentiment fallback normalized result:", result);
    return result;
  } catch (error) {
    console.error("❌ [API] Sentiment history error details:", {
      message: error.message,
      status: error.response?.status,
      url: error.config?.url,
      method: error.config?.method,
    });
    const errorMessage = handleApiError(error, "get market sentiment history");
    return { data: null };
  }
};

export const getMarketSectorPerformance = async () => {
  console.log(`📊 [API] Fetching market sector performance...`);

  try {
    const response = await api.get(`/api/sectors/sectors-with-history/performance`);
    console.log(`📊 [API] Fetched sector performance:`, response.data);

    // Always return { data: ... } structure for consistency
    if (response?.data && typeof response?.data === "object") {
      console.log("📊 [API] Returning sector data structure:", response?.data);
      return response?.data;
    }

    // Fallback to normalized response
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    console.log("📊 [API] Sector fallback normalized result:", result);
    return result;
  } catch (error) {
    console.error("❌ [API] Sector performance error details:", {
      message: error.message,
      status: error.response?.status,
      url: error.config?.url,
      method: error.config?.method,
    });
    const errorMessage = handleApiError(error, "get market sector performance");
    return { data: null };
  }
};

export const getMarketBreadth = async () => {
  console.log(`📊 [API] Fetching market breadth...`);

  try {
    const response = await api.get(`/api/market/breadth`);
    console.log(`📊 [API] Fetched market breadth:`, response.data);

    // Use normalized response handler - handles all response format variations
    const breadthData = extractResponseData(response);
    if (!breadthData) {
      console.error("❌ [API] Market breadth returned no data");
      return { data: null, success: false };
    }
    console.log("📊 [API] Returning breadth data:", breadthData);
    return breadthData;
  } catch (error) {
    console.error("❌ [API] Market breadth error details:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
      url: error.config?.url,
      method: error.config?.method,
    });
    const errorMessage = handleApiError(error, "get market breadth");
    return { data: null };
  }
};

export const getMarketInternals = async () => {
  console.log(`📊 [API] Fetching market internals...`);

  try {
    const response = await api.get(`/api/market/internals`);
    console.log(`📊 [API] Fetched market internals:`, response.data);

    // Always return response as-is for internals
    if (response?.data && typeof response?.data === "object") {
      console.log("📊 [API] Returning internals data structure:", response?.data);
      return response?.data;
    }

    // Fallback to normalized response
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    console.log("📊 [API] Internals fallback normalized result:", result);
    return result;
  } catch (error) {
    console.error("❌ [API] Market internals error details:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
      url: error.config?.url,
      method: error.config?.method,
    });
    const errorMessage = handleApiError(error, "get market internals");
    return { data: null };
  }
};

export const getDistributionDays = async () => {
  console.log(`📊 [API] Fetching distribution days...`);

  try {
    console.log(`📊 [API] Calling /api/market/distribution-days`);
    const response = await api.get(`/api/market/distribution-days`);
    console.log(`📊 [API] Distribution days response:`, response);

    // Use normalized response handler - handles all response format variations
    const distData = extractResponseData(response);
    if (!distData) {
      console.error("❌ [API] Distribution days returned no data");
      return { data: null, success: false };
    }
    console.log("📊 [API] Returning distribution days data:", distData);
    return distData;
  } catch (error) {
    console.error("❌ [API] Distribution days error details:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
      url: error.config?.url,
      method: error.config?.method,
    });
    const errorMessage = handleApiError(error, "get distribution days");
    return { data: null };
  }
};

export const getEconomicIndicators = async (days = 90) => {
  console.log(`📊 [API] Fetching economic indicators for ${days} days...`);

  try {
    const response = await api.get(`/api/market/economic?days=${days}`);
    console.log(`📊 [API] Fetched economic indicators:`, response.data);

    // Always return { data: ... } structure for consistency
    if (response?.data && typeof response?.data === "object") {
      console.log("📊 [API] Returning economic data structure:", response?.data);
      return response?.data;
    }

    // Fallback to normalized response
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    console.log("📊 [API] Economic fallback normalized result:", result);
    return result;
  } catch (error) {
    console.error("❌ [API] Economic indicators error details:", {
      message: error?.message || "Unknown error",
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

export const getMarketCorrelation = async (symbols = null, period = "1y") => {
  console.log(
    `📈 [API] Fetching market correlation analysis for period: ${period}...`
  );

  try {
    const params = new URLSearchParams();
    if (symbols) params.append("symbols", symbols);
    if (period) params.append("period", period);

    const queryString = params.toString();
    const endpoint = `/api/market/correlation${queryString ? "?" + queryString : ""}`;

    const response = await api.get(endpoint);

    console.log("📈 [API] Market correlation response:", {
      success: response?.success,
      hasData: !!response.data,
      hasCorrelationMatrix: !!response.data?.correlation_matrix,
    });

    return response;
  } catch (error) {
    console.error("📈 [API] Market correlation error:", error);
    const errorMessage = handleApiError(error, "get market correlation");
    return {
      success: false,
      data: {},
      error: errorMessage,
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
        message: lastError?.message || "Unknown error",
        status: lastError.response?.status,
        url: lastError.config?.url,
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
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    console.log("📅 [API] Seasonality fallback normalized result:", result);
    return result;
  } catch (error) {
    console.error("❌ [API] Seasonality error details:", {
      message: error?.message || "Unknown error",
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

// Yield Curve Spread endpoint
export const getYieldCurveData = async () => {
  console.log("📈 [API] Fetching yield curve data...");

  try {
    const response = await api.get("/api/market/overview");

    if (response?.data?.yield_curve) {
      console.log("📈 [API] Fetched yield curve data:", response?.data?.yield_curve);
      return {
        success: true,
        data: response?.data?.yield_curve,
        timestamp: new Date().toISOString()
      };
    }

    return null;
  } catch (error) {
    console.error("❌ [API] Yield curve error:", error?.message);
    return {
      success: false,
      data: null,
      error: error?.message || "Failed to fetch yield curve data",
      timestamp: new Date().toISOString()
    };
  }
};

// McClellan Oscillator endpoint
export const getMcClellanOscillator = async () => {
  console.log("📊 [API] Fetching McClellan Oscillator...");

  try {
    const response = await api.get("/api/market/mcclellan-oscillator");
    console.log("📊 [API] Fetched McClellan Oscillator:", response.data);
    return extractResponseData(response);
  } catch (error) {
    console.error("❌ [API] McClellan Oscillator error:", error?.message);
    return {
      success: false,
      data: null,
      error: error?.message || "Failed to fetch McClellan Oscillator",
      timestamp: new Date().toISOString()
    };
  }
};

// Sentiment Divergence endpoint
export const getSentimentDivergence = async () => {
  console.log("💡 [API] Fetching sentiment divergence...");

  try {
    const response = await api.get("/api/sentiment/divergence");
    console.log("💡 [API] Fetched sentiment divergence:", response.data);
    return extractResponseData(response);
  } catch (error) {
    console.error("❌ [API] Sentiment divergence error:", error?.message);
    return {
      success: false,
      data: null,
      error: error?.message || "Failed to fetch sentiment divergence",
      timestamp: new Date().toISOString()
    };
  }
};

export const getMarketResearchIndicators = async () => {
  console.log("🔬 [API] Fetching market research indicators...");

  try {
    // Use the correct endpoint for our API
    const endpoints = ["/api/market/research-indicators"];

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
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    console.log(
      "🔬 [API] Research indicators fallback normalized result:",
      result
    );
    return result;
  } catch (error) {
    console.error("❌ [API] Research indicators error details:", {
      message: error?.message || "Unknown error",
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
    const endpoints = [`/api/stocks?${queryParams.toString()}`];

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
      status: response?.status,
      hasData: !!response?.data,
      dataType: typeof response?.data,
      dataKeys: response?.data ? Object.keys(response?.data) : [],
    });

    // Use normalized response handler
    const normalizedData = extractResponseData(response);
    if (normalizedData) {
      console.log("✅ getStocks: returning normalized data:", normalizedData);
      return normalizedData;
    }

    // Return empty structure if no data
    return { stocks: [], viewType: "list" };
  } catch (error) {
    console.error("❌ Error fetching stocks:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
      url: error.config?.url,
      method: error.config?.method,
      stack: error?.stack?.substring(0, 500) + "...",
    });
    const errorMessage = handleApiError(error, "get stocks");
    return { data: null };
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
    const responseData = extractResponseData(response);
    return {
      data: responseData || null,
      success: true
    };
  } catch (error) {
    const errorMessage = handleApiError(error, "get stocks quick");
    return { data: null };
  }
};

// Chunked stocks loading
export const getStocksChunk = async (chunkIndex = 0) => {
  try {
    const response = await api.get(`/api/stocks/chunk/${chunkIndex}`);
    const responseData = extractResponseData(response);
    return {
      data: responseData || null,
      success: true
    };
  } catch (error) {
    const errorMessage = handleApiError(error, "get stocks chunk");
    return { data: null };
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
    const responseData = extractResponseData(response);
    return {
      data: responseData || null,
      success: true
    };
  } catch (error) {
    const errorMessage = handleApiError(error, "get stocks full");
    return { data: null };
  }
};

export const getStock = async (ticker) => {
  console.log("🚀 getStock: Starting API call for ticker:", ticker);
  try {
    const response = await api.get(`/api/stocks/${ticker}`);
    console.log("📊 getStock: Raw response:", {
      status: response?.status,
      hasData: !!response?.data,
      dataType: typeof response?.data,
      dataKeys: response?.data ? Object.keys(response?.data) : [],
    });

    // Always return { data: ... } structure for consistency
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    }; // Single stock is an object
    console.log("✅ getStock: returning result:", result);
    return result;
  } catch (error) {
    console.error("❌ Error fetching stock:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
      url: error.config?.url,
      method: error.config?.method,
      stack: error?.stack?.substring(0, 500) + "...",
    });
    const errorMessage = handleApiError(error, "get stock");
    return { data: null };
  }
};

// Removed: getStockProfile - StockDetail page no longer exists
// This function was calling the deprecated /api/price/:ticker endpoint

export const getStockMetrics = async (ticker) => {
  try {
    // Use /api/scores/stockscores with search parameter for metrics and scores data
    const response = await api.get(`/api/scores/stockscores?search=${ticker}&limit=1`);
    const stocks = response.data?.items ?? extractResponseData(response) ?? [];
    const stock = stocks.length > 0 ? stocks[0] : null;

    if (!stock) {
      return { data: null, success: false };
    }

    const result = {
      data: stock,
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    return {
      data: result || {},
      success: true
    };
  } catch (error) {
    console.error(`Stock metrics error for ${ticker}:`, error);
    return { data: null };
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
      status: response?.status,
      hasData: !!response?.data,
      dataType: typeof response?.data,
      dataKeys: response?.data ? Object.keys(response?.data) : [],
    });

    // Always return { data: ... } structure for consistency
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    console.log("✅ getStockFinancials: returning result:", result);
    return result;
  } catch (error) {
    console.error("❌ Error fetching stock financials:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
      url: error.config?.url,
      method: error.config?.method,
      stack: error?.stack?.substring(0, 500) + "...",
    });
    const errorMessage = handleApiError(error, "get stock financials");
    return { data: null };
  }
};

export const getAnalystRecommendations = async (ticker) => {
  try {
    const response = await api.get(`/api/analysts/${ticker}/recommendations`);
    // Always return { data: ... } structure for consistency
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    return result;
  } catch (error) {
    const errorMessage = handleApiError(error, "get analyst recommendations");
    return { data: null };
  }
};

// Removed: getStockPrices - StockDetail page no longer exists
// This function was calling the deprecated /api/price/history endpoint

// Removed: getStockPricesRecent - was an alias for getStockProfile (also removed)

export const getStockRecommendations = async (ticker) => {
  try {
    const response = await api.get(`/api/stocks/${ticker}/recommendations`);
    // Always return { data: ... } structure for consistency
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    return result;
  } catch (error) {
    const errorMessage = handleApiError(error, "get stock recommendations");
    return { data: null };
  }
};

export const getSectors = async () => {
  try {
    const response = await api.get("/api/stocks/sectors");
    // Always return { data: ... } structure for consistency
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    return result;
  } catch (error) {
    const errorMessage = handleApiError(error, "get sectors");
    return { data: null };
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
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    return result;
  } catch (error) {
    const errorMessage = handleApiError(error, "get valuation metrics");
    return { data: null };
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
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    return result;
  } catch (error) {
    const errorMessage = handleApiError(error, "get growth metrics");
    return { data: null };
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
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    return result;
  } catch (error) {
    const errorMessage = handleApiError(error, "get dividend metrics");
    return { data: null };
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
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    return result;
  } catch (error) {
    const errorMessage = handleApiError(
      error,
      "get financial strength metrics"
    );
    return { data: null };
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
      `/api/earnings/info?${queryParams.toString()}`,
      {
        baseURL: currentConfig.baseURL,
      }
    );
    // Always return { data: ... } structure for consistency
    const result = {
      data: response.data?.data?.estimates || [],
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    return result;
  } catch (error) {
    const errorMessage = handleApiError(error, "get earnings estimates");
    return { data: null };
  }
};

export const getRevenueEstimates = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        queryParams.append(key, value);
      }
    });
    const response = await api.get(
      `/api/earnings/revenue-estimates?${queryParams.toString()}`,
      {
        baseURL: currentConfig.baseURL,
      }
    );
    // Always return { data: ... } structure for consistency
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    return result;
  } catch (error) {
    const errorMessage = handleApiError(error, "get revenue estimates");
    return { data: null };
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
      `/api/earnings/history?${queryParams.toString()}`,
      {
        baseURL: currentConfig.baseURL,
      }
    );
    // Always return { data: ... } structure for consistency
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    return result;
  } catch (error) {
    const errorMessage = handleApiError(error, "get earnings history");
    return { data: null };
  }
};

// Ticker-based endpoints (wrap Axios promise for consistency)
export const getTickerEarningsEstimates = async (ticker) => {
  try {
    const response = await api.get(
      `/api/analysts/${ticker}/earnings-estimates`
    );
    // Always return { data: ... } structure for consistency
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    return result;
  } catch (error) {
    const errorMessage = handleApiError(error, "get ticker earnings estimates");
    return { data: null };
  }
};

export const getTickerEarningsHistory = async (ticker) => {
  try {
    const response = await api.get(`/api/analysts/${ticker}/earnings-history`);
    // Always return { data: ... } structure for consistency
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    return result;
  } catch (error) {
    const errorMessage = handleApiError(error, "get ticker earnings history");
    return { data: null };
  }
};

export const getTickerRevenueEstimates = async (ticker) => {
  try {
    const response = await api.get(`/api/analysts/${ticker}/revenue-estimates`);
    // Always return { data: ... } structure for consistency
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    return result;
  } catch (error) {
    const errorMessage = handleApiError(error, "get ticker revenue estimates");
    return { data: null };
  }
};

export const getTickerEpsRevisions = async (ticker) => {
  try {
    const response = await api.get(`/api/analysts/${ticker}/eps-revisions`);
    // Always return { data: ... } structure for consistency
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    return result;
  } catch (error) {
    const errorMessage = handleApiError(error, "get ticker eps revisions");
    return { data: null };
  }
};

export const getTickerEpsTrend = async (ticker) => {
  try {
    const response = await api.get(`/api/analysts/${ticker}/eps-trend`);
    // Always return { data: ... } structure for consistency
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    return result;
  } catch (error) {
    const errorMessage = handleApiError(error, "get ticker eps trend");
    return { data: null };
  }
};

export const getTickerGrowthEstimates = async (ticker) => {
  try {
    const response = await api.get(`/api/analysts/${ticker}/growth-estimates`);
    // Always return { data: ... } structure for consistency
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    return result;
  } catch (error) {
    const errorMessage = handleApiError(error, "get ticker growth estimates");
    return { data: null };
  }
};

export const getTickerAnalystRecommendations = async (ticker) => {
  try {
    const response = await api.get(`/api/analysts/${ticker}/recommendations`);
    // Always return { data: ... } structure for consistency
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    return result;
  } catch (error) {
    const errorMessage = handleApiError(
      error,
      "get ticker analyst recommendations"
    );
    return { data: null };
  }
};

export const getAnalystOverview = async (ticker) => {
  console.log(`📊 [API] Fetching analyst overview for ${ticker}...`);
  try {
    // Fetch ONLY from endpoints that have REAL data - NO FAKE FALLBACKS for financial data
    const infoResponse = await api.get(`/api/earnings/info?symbol=${ticker}`).catch(() => ({ data: { data: { history: [], estimates: [] } } }));

    // Extract real data from responses
    const earningsHistory = Array.isArray(infoResponse.data?.data?.history)
      ? infoResponse.data.data.history
      : [];

    const earningsEstimates = Array.isArray(infoResponse.data?.data?.estimates)
      ? infoResponse.data.data.estimates
      : [];

    // Return ONLY real data - no placeholder data for missing endpoints
    const result = {
      data: {
        earnings_history: earningsHistory,
        earnings_estimates: earningsEstimates
      },
      success: true,
      timestamp: new Date().toISOString()
    };

    console.log(`✅ [API] Analyst overview for ${ticker}:`, result);
    return result;
  } catch (error) {
    console.error(`❌ [API] Analyst overview error for ${ticker}:`, error);
    // Return null on error - never fake data for financial information
    return { data: null };
  }
};

export const getFinancialStatements = async (ticker, period = "annual") => {
  try {
    const response = await api.get(
      `/api/financials/${ticker}/statements?period=${period}`
    );
    // Always return { data: ... } structure for consistency
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    return result;
  } catch (error) {
    const errorMessage = handleApiError(error, "get financial statements");
    return { data: null };
  }
};

export const getIncomeStatement = async (ticker, period = "annual") => {
  try {
    const response = await api.get(
      `/api/financials/${ticker}/income-statement?period=${period}`
    );
    // Extract data array from API response: { success, data: { financialData: [...], ... } }
    const wrappedData = response.data?.data || {};
    const result = wrappedData.financialData || wrappedData.data || [];

    // Transform data to match frontend expectations (add items property)
    const transformedData = Array.isArray(result)
      ? result.map(period => ({
          ...period,
          items: Object.fromEntries(
            Object.entries(period).filter(([key]) =>
              !['symbol', 'date', 'raw'].includes(key)
            )
          )
        }))
      : result;

    return transformedData;
  } catch (error) {
    const errorMessage = handleApiError(error, "get income statement");
    return { data: null };
  }
};

export const getCashFlowStatement = async (ticker, period = "annual") => {
  try {
    const response = await api.get(
      `/api/financials/${ticker}/cash-flow?period=${period}`
    );
    // Extract data array from API response: { success, data: { financialData: [...], ... } }
    const wrappedData = response.data?.data || {};
    const result = wrappedData.financialData || wrappedData.data || [];

    // Transform data to match frontend expectations (add items property)
    const transformedData = Array.isArray(result)
      ? result.map(period => ({
          ...period,
          items: Object.fromEntries(
            Object.entries(period).filter(([key]) =>
              !['symbol', 'date', 'raw'].includes(key)
            )
          )
        }))
      : result;

    return transformedData;
  } catch (error) {
    const errorMessage = handleApiError(error, "get cash flow statement");
    return { data: null };
  }
};

export const getBalanceSheet = async (ticker, period = "annual") => {
  try {
    const response = await api.get(
      `/api/financials/${ticker}/balance-sheet?period=${period}`
    );
    // Extract data array from API response: { success, data: { financialData: [...], ... } }
    const wrappedData = response.data?.data || {};
    const result = wrappedData.financialData || wrappedData.data || [];

    // Transform data to match frontend expectations (add items property)
    const transformedData = Array.isArray(result)
      ? result.map(period => ({
          ...period,
          items: Object.fromEntries(
            Object.entries(period).filter(([key]) =>
              !['symbol', 'date', 'raw'].includes(key)
            )
          )
        }))
      : result;

    return transformedData;
  } catch (error) {
    const errorMessage = handleApiError(error, "get balance sheet");
    return { data: null };
  }
};

export const getKeyMetrics = async (ticker) => {
  try {
    const url = `/api/financials/${ticker}/key-metrics`;
    const response = await api.get(url, {
      baseURL: currentConfig.baseURL,
    });
    // Extract data from API response: { success, data: { metricsData: {...}, ... } }
    // Key metrics returns an object, not array
    const wrappedData = response.data?.data || {};
    const result = wrappedData.metricsData || wrappedData.data;
    return result;
  } catch (error) {
    const errorMessage = handleApiError(error, `get key metrics for ${ticker}`);
    return { data: null };
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
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    return result;
  } catch (error) {
    const errorMessage = handleApiError(error, "get all financial data");
    return { data: null };
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
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    return result;
  } catch (error) {
    const errorMessage = handleApiError(error, "get financial metrics");
    return { data: null };
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
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    return result;
  } catch (error) {
    const errorMessage = handleApiError(error, "get EPS revisions");
    return { data: null };
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
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    return result;
  } catch (error) {
    const errorMessage = handleApiError(error, "get EPS trend");
    return { data: null };
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
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    return result;
  } catch (error) {
    const errorMessage = handleApiError(error, "get growth estimates");
    return { data: null };
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
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    return result;
  } catch (error) {
    const errorMessage = handleApiError(error, "get economic data");
    return { data: null };
  }
};

// --- STOCK API FUNCTIONS ---
export const getStockInfo = async (symbol) => {
  console.log(`ℹ️ [API] Fetching stock info for ${symbol}...`);
  try {
    const response = await api.get(`/stocks/info/${symbol}`);
    console.log(`ℹ️ [API] Stock info response for ${symbol}:`, response);
    return normalizeResponse(response, false);
  } catch (error) {
    console.error(`❌ [API] Stock info error for ${symbol}:`, {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    return { data: null };
  }
};

// Removed: getStockPrice - was an alias for getStockProfile (also removed)

export const getStockHistory = async (symbol) => {
  console.log(`📊 [API] Fetching stock history for ${symbol}...`);
  try {
    const response = await api.get(`/stocks/history/${symbol}`);
    console.log(`📊 [API] Stock history response for ${symbol}:`, response);
    return normalizeResponse(response, true);
  } catch (error) {
    console.error(`❌ [API] Stock history error for ${symbol}:`, {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    return { data: null };
  }
};

export const searchStocks = async (query) => {
  console.log(`🔍 [API] Searching stocks with query: ${query}...`);
  try {
    const response = await api.get(
      `/stocks/search?q=${encodeURIComponent(query)}`
    );
    console.log(`🔍 [API] Stock search response:`, response);
    return normalizeResponse(response, true);
  } catch (error) {
    console.error(`❌ [API] Stock search error:`, {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    return { data: null };
  }
};

// --- HEALTH CHECK ---
export const getHealth = async () => {
  console.log("🏥 [API] Checking API health...");
  try {
    const response = await api.get("/api/health");
    console.log("🏥 [API] Health check response:", response);
    return normalizeResponse(response, false);
  } catch (error) {
    console.error("❌ [API] Health check error:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    return { data: null };
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
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    }; // Array of NAAIM data
    return result;
  } catch (error) {
    const errorMessage = handleApiError(error, "get NAAIM data");
    return { data: null };
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
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    }; // Array of fear/greed data
    return result;
  } catch (error) {
    const errorMessage = handleApiError(error, "get fear & greed data");
    return { data: null };
  }
};

// Get price history data from price_daily/weekly/monthly tables
// NOTE: getPriceHistory() and getTechnicalData() have been removed
// Use sector or stock endpoint for price data

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

    if (!healthResponse?.ok) {
      return null;
    }

    const healthData = await healthResponse.json();
    console.log("✅ [API] API initialized successfully:", healthData);
    return healthData;
  } catch (error) {
    console.error("❌ [API] API initialization failed:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    return { data: null };
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
      status: response?.status,
      data: response?.data,
      message: "API connection successful",
    };
  } catch (error) {
    console.error("API connection test failed:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
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

// Diagnostic function
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
    return { data: null };
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
  const response = await api.get("/api/health/full");
  // Always return { data: ... } structure for consistency
  const result = normalizeResponse(response, false);
  return result;
};


export const getRecentAnalystActions = async (limit = 10) => {
  try {
    const response = await api.get(
      `/api/analysts/recent-actions?limit=${limit}`
    );
    // Always return { data: ... } structure for consistency
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    }; // Expect array of analyst actions
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
    // Test sectors endpoint (technical data endpoint removed)
    const sectorsResponse = await api.get("/api/sectors");
    results.sectors = { success: true, data: sectorsResponse?.data };
  } catch (error) {
    results.sectors = { success: false, error: error.message };
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
      status: response?.status,
      hasData: !!response?.data,
      dataType: typeof response?.data,
      dataKeys: response?.data ? Object.keys(response?.data) : [],
    });

    // Always return { data: ... } structure for consistency
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    console.log("✅ getMarketIndices: returning result:", result);
    return result;
  } catch (error) {
    console.error("❌ Error fetching market indices:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      url: error.config?.url,
    });
    const errorMessage = handleApiError(error, "get market indices");
    return { data: null };
  }
};

// Market volatility
export const getMarketVolatility = async () => {
  console.log("🚀 getMarketVolatility: Starting API call...");
  try {
    const response = await api.get("/api/market/volatility");

    console.log("📊 getMarketVolatility: Raw response:", {
      status: response?.status,
      hasData: !!response?.data,
      dataType: typeof response?.data,
      dataKeys: response?.data ? Object.keys(response?.data) : [],
    });

    // Always return { data: ... } structure for consistency
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    console.log("✅ getMarketVolatility: returning result:", result);
    return result;
  } catch (error) {
    console.error("❌ Error fetching market volatility:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    const errorMessage = handleApiError(error, "get market volatility");
    return { data: null };
  }
};

// Economic calendar
export const getEconomicCalendar = async () => {
  console.log("🚀 getEconomicCalendar: Starting API call...");
  try {
    const response = await api.get("/api/economic/calendar");

    console.log("📊 getEconomicCalendar: Raw response:", {
      status: response?.status,
      hasData: !!response?.data,
      dataType: typeof response?.data,
      dataKeys: response?.data ? Object.keys(response?.data) : [],
    });

    // Always return { data: ... } structure for consistency
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    console.log("✅ getEconomicCalendar: returning result:", result);
    return result;
  } catch (error) {
    console.error("❌ Error fetching economic calendar:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    const errorMessage = handleApiError(error, "get economic calendar");
    return { data: null };
  }
};

// Market cap categories
export const getMarketCapCategories = async () => {
  console.log("🚀 getMarketCapCategories: Starting API call...");
  try {
    const response = await api.get("/api/stocks/market-cap-categories");

    console.log("📊 getMarketCapCategories: Raw response:", {
      status: response?.status,
      hasData: !!response?.data,
      dataType: typeof response?.data,
      dataKeys: response?.data ? Object.keys(response?.data) : [],
    });

    // Always return { data: ... } structure for consistency
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    console.log("✅ getMarketCapCategories: returning result:", result);
    return result;
  } catch (error) {
    console.error("❌ Error fetching market cap categories:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    const errorMessage = handleApiError(error, "get market cap categories");
    return { data: null };
  }
};

// Technical indicators
// Volume data
export const getVolumeData = async (symbol, timeframe) => {
  console.log("🚀 getVolumeData: Starting API call...", { symbol, timeframe });
  try {
    const response = await api.get(`/api/stocks/${symbol}/volume`, {
      params: { timeframe },
    });

    console.log("📊 getVolumeData: Raw response:", {
      status: response?.status,
      hasData: !!response?.data,
      dataType: typeof response?.data,
      dataKeys: response?.data ? Object.keys(response?.data) : [],
    });

    // Always return { data: ... } structure for consistency
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    console.log("✅ getVolumeData: returning result:", result);
    return result;
  } catch (error) {
    console.error("❌ Error fetching volume data:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    const errorMessage = handleApiError(error, "get volume data");
    return { data: null };
  }
};

// Support resistance levels - DEPRECATED
// Removed: /api/technical endpoint no longer exists
// export const getSupportResistanceLevels = async (symbol) => { ... }

// --- DASHBOARD API FUNCTIONS ---
export const getDashboardSummary = async () => {
  console.log("📊 [API] Fetching dashboard summary...");
  try {
    const response = await api.get("/api/dashboard/summary");
    console.log("📊 [API] Dashboard summary response:", response);
    // Always return { data: ... } structure for consistency
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    return result;
  } catch (error) {
    console.error("❌ [API] Dashboard summary error:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    return { data: null };
  }
};

export const getDashboardPerformance = async () => {
  console.log("📈 [API] Fetching dashboard performance...");
  try {
    const response = await api.get("/api/dashboard/performance");
    console.log("📈 [API] Dashboard performance response:", response);
    // Always return { data: ... } structure for consistency
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    return result;
  } catch (error) {
    console.error("❌ [API] Dashboard performance error:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    return { data: null };
  }
};

export const getDashboardAlerts = async () => {
  console.log("🚨 [API] Fetching dashboard alerts...");
  try {
    const response = await api.get("/api/dashboard/alerts");
    console.log("🚨 [API] Dashboard alerts response:", response);
    // Always return { data: ... } structure for consistency
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    return result;
  } catch (error) {
    console.error("❌ [API] Dashboard alerts error:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    return { data: null };
  }
};

export const getDashboardDebug = async () => {
  console.log("🔧 [API] Fetching dashboard debug info...");
  try {
    const response = await api.get("/api/dashboard/debug");
    console.log("🔧 [API] Dashboard debug response:", response);
    // Always return { data: ... } structure for consistency
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    return result;
  } catch (error) {
    console.error("❌ [API] Dashboard debug error:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    return { data: null };
  }
};

// --- MARKET API FUNCTIONS ---
export const getMarketIndicators = async () => {
  console.log("📊 [API] Fetching market indicators...");
  try {
    const response = await api.get("/api/market/indicators");
    console.log("📊 [API] Market indicators response:", response);
    // Always return { data: ... } structure for consistency
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    return result;
  } catch (error) {
    console.error("❌ [API] Market indicators error:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      url: error.config?.url,
    });
    return { data: null };
  }
};

// UNIFIED MARKET DATA ENDPOINT - Get all market data in one call
export const getUnifiedMarketData = async () => {
  console.log("📊 [API] Fetching unified market data...");
  try {
    const response = await api.get("/api/market/data");
    console.log("📊 [API] Unified market data response:", response);
    // Return the full response structure with consolidated market data
    const result = {
      data: response.data?.data || {},
      success: response.data?.success ?? true,
      timestamp: response.data?.data?.data_timestamp,
      fetch_time_ms: response.data?.data?.fetch_time_ms
    };
    return result;
  } catch (error) {
    console.error("❌ [API] Unified market data error:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      url: error.config?.url,
    });
    return { data: null };
  }
};

export const getMarketSentiment = async () => {
  console.log("😊 [API] Fetching market sentiment...");
  try {
    const response = await api.get('/api/sentiment/current');
    return extractResponseData(response);
  } catch (error) {
    console.error("❌ [API] Market sentiment error:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      url: error.config?.url,
    });
    return { data: null };
  }
};

// NEW FOCUSED MARKET ENDPOINTS - 3-endpoint architecture
export const getMarketTechnicals = async () => {
  console.log("📊 [API] Fetching market technicals...");
  try {
    const response = await api.get("/api/market/technicals");
    return { data: response.data?.data || {}, success: response.data?.success ?? true, timestamp: response.data?.data?.timestamp };
  } catch (error) {
    console.error("❌ [API] Market technicals error:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      url: error.config?.url,
    });
    return { data: null };
  }
};

export const getMarketSentimentData = async (range = "30d") => {
  console.log("😊 [API] Fetching market sentiment data...");
  try {
    const response = await api.get(`/api/market/sentiment?range=${range}`);
    return { data: response.data?.data || {}, success: response.data?.success ?? true, range: response.data?.range || range, timestamp: response.data?.timestamp };
  } catch (error) {
    console.error("❌ [API] Market sentiment data error:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      url: error.config?.url,
    });
    return { data: null };
  }
};

export const getMarketSeasonalityData = async () => {
  console.log("📅 [API] Fetching market seasonality data...");
  try {
    const response = await api.get("/api/market/seasonality");
    return { data: response.data?.data || {}, success: response.data?.success ?? true, timestamp: response.data?.data?.timestamp };
  } catch (error) {
    console.error("❌ [API] Market seasonality data error:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      url: error.config?.url,
    });
    return { data: null };
  }
};

// --- FINANCIAL DATA API FUNCTIONS ---
export const getFinancialData = async (symbol) => {
  console.log(`💰 [API] Fetching financial data for ${symbol}...`);
  try {
    const response = await api.get(`/financials/data/${symbol}`);
    console.log(`💰 [API] Financial data response for ${symbol}:`, response);
    // Always return { data: ... } structure for consistency
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    return result;
  } catch (error) {
    console.error(`❌ [API] Financial data error for ${symbol}:`, {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      url: error.config?.url,
      symbol,
    });
    return { data: null };
  }
};

export const getEarningsData = async (symbol) => {
  console.log(`📊 [API] Fetching earnings data for ${symbol}...`);
  try {
    const response = await api.get(`/financials/earnings/${symbol}`);
    console.log(`📊 [API] Earnings data response for ${symbol}:`, response);
    // Always return { data: ... } structure for consistency
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    return result;
  } catch (error) {
    console.error(`❌ [API] Earnings data error for ${symbol}:`, {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    return { data: null };
  }
};

export const getCashFlow = async (symbol) => {
  console.log(`💵 [API] Fetching cash flow for ${symbol}...`);
  try {
    const response = await api.get(`/financials/cash-flow/${symbol}`);
    console.log(`💵 [API] Cash flow response for ${symbol}:`, response);
    // Always return { data: ... } structure for consistency
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    return result;
  } catch (error) {
    console.error(`❌ [API] Cash flow error for ${symbol}:`, {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    return { data: null };
  }
};

// --- MISSING DASHBOARD API FUNCTIONS ---
export const getDashboardUser = async () => {
  console.log("👤 [API] Fetching dashboard user...");
  try {
    const response = await api.get('/api/user/profile');
    return extractResponseData(response);
  } catch (error) {
    console.error("❌ [API] Dashboard user error:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    return { data: null };
  }
};

export const getDashboardHoldings = async () => {
  console.log("📈 [API] Fetching dashboard holdings...");
  try {
    const response = await api.get('/api/portfolio/holdings');
    return extractResponseData(response);
  } catch (error) {
    console.error("❌ [API] Dashboard holdings error:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    return { data: null };
  }
};

export const getDashboardUserSettings = async () => {
  console.log("⚙️ [API] Fetching dashboard user settings...");
  try {
    const response = await api.get('/api/user/settings');
    return extractResponseData(response);
  } catch (error) {
    console.error("❌ [API] Dashboard user settings error:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    return { data: null };
  }
};

export const getDashboardMarketSummary = async () => {
  console.log("📈 [API] Fetching dashboard market summary...");
  try {
    const response = await api.get('/api/market/summary');
    return extractResponseData(response);
  } catch (error) {
    console.error("❌ [API] Dashboard market summary error:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    return { data: null };
  }
};

export const getDashboardEarningsCalendar = async () => {
  console.log("📅 [API] Fetching dashboard earnings calendar...");
  try {
    const response = await api.get("/api/earnings/calendar");
    console.log("📅 [API] Earnings calendar response:", response.data);
    // Backend returns: { items: [...calendar items], pagination: {...}, success: true }
    return response.data?.items || [];
  } catch (error) {
    console.error("❌ [API] Dashboard earnings calendar error:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    return [];
  }
};

export const getDashboardFinancialHighlights = async () => {
  console.log("💰 [API] Fetching dashboard financial highlights...");
  try {
    const response = await api.get("/api/financials/highlights");
    console.log("💰 [API] Financial highlights response:", response.data);
    return extractResponseData(response);
  } catch (error) {
    console.error("❌ [API] Dashboard financial highlights error:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    return { data: null };
  }
};

export const getDashboardSymbols = async () => {
  console.log("🔤 [API] Fetching dashboard symbols...");
  try {
    const response = await api.get("/api/dashboard/symbols");
    console.log("🔤 [API] Dashboard symbols response:", response.data);
    return extractResponseData(response);
  } catch (error) {
    console.error("❌ [API] Dashboard symbols error:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    return { data: null };
  }
};

export const getTradingSignalsDaily = async (params = {}) => {
  console.log("📈 [API] Fetching daily trading signals...", params);

  try {
    const queryParams = new URLSearchParams({
      limit: params.limit || 10,
      timeframe: 'daily',
      ...params,
    }).toString();

    const endpoint = `/api/signals/stocks?${queryParams}`;
    console.log(`📈 [API] Using endpoint: ${endpoint}`);
    const response = await api.get(endpoint);
    console.log(`📈 [API] SUCCESS with endpoint: ${endpoint}`, response);

    console.log("📈 [API] Trading signals daily raw response:", response);
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    console.log("📈 [API] Trading signals daily normalized result:", result);
    return result;
  } catch (error) {
    console.error("❌ [API] Trading signals daily error details:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
      url: error.config?.url,
      method: error.config?.method,
      stack: error?.stack?.substring(0, 500) + "...",
    });
    return { data: null };
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
      console.error(
        "👤 [API] All endpoints failed, throwing last error:",
        lastError
      );
      throw lastError;
    }

    console.log("👤 [API] Current user raw response:", response);
    const result = {
      data: extractResponseData(response),
      success: response.data?.success ?? true,
      timestamp: response.data?.timestamp
    };
    console.log("👤 [API] Current user normalized result:", result);
    return result;
  } catch (error) {
    console.error("❌ [API] Current user error details:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
      url: error.config?.url,
      method: error.config?.method,
      stack: error?.stack?.substring(0, 500) + "...",
    });
    return { data: null };
  }
};

export const getDashboardTechnicalSignals = async () => {
  console.log("📊 [API] Fetching dashboard technical signals...");
  try {
    const response = await api.get('/api/signals/dashboard');
    return extractResponseData(response);
  } catch (error) {
    console.error("❌ [API] Dashboard technical signals error:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    return { data: null };
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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    return { data: null };
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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    return { data: null };
  }
};


// Export all methods as a default object for easier importing

// Add aliases for test compatibility - fetchXxx functions expected by tests
// fetchMarketOverview is exported from api.js, not apiPart2.js
export const fetchStockData = getStock;
export const fetchMarketData = getMarketIndicators;
export const fetchEarningsData = getEarningsData;
export const fetchHistoricalData = getStockHistory;

// Check if Alpaca is configured (using environment variables)
export const checkAlpacaConfiguration = async () => {
  try {
    const response = await api.get("/api/portfolio/import/alpaca/status");
    return extractResponseData(response);
  } catch (error) {
    console.error("Error checking Alpaca configuration:", error);
    return { data: null };
  }
};

// Market Commentary functions
export const getMarketCommentary = async (
  category = "all",
  period = "week"
) => {
  try {
    const response = await api.get("/api/research/commentary", {
      params: { category, period },
    });
    return extractResponseData(response);
  } catch (error) {
    return { data: null };
  }
};

export const getMarketTrends = async (period = "week") => {
  try {
    const response = await api.get("/api/research/trends", {
      params: { period },
    });
    return extractResponseData(response);
  } catch (error) {
    return { data: null };
  }
};

export const getAnalystOpinions = async () => {
  try {
    const response = await api.get("/api/research/analysts");
    return extractResponseData(response);
  } catch (error) {
    return { data: null };
  }
};

export const subscribeToCommentary = async (category = "all") => {
  try {
    const response = await api.post("/api/research/commentary/subscribe", {
      category,
    });
    return extractResponseData(response);
  } catch (error) {
    console.error("Error subscribing to commentary:", error);
    return { data: null };
  }
};

export const getOrderBook = async (symbol) => {
  try {
    const response = await api.get(`/api/trading/orderbook/${symbol}`);
    return extractResponseData(response);
  } catch (error) {
    return { data: null };
  }
};

export const getTradingPositions = async () => {
  try {
    const response = await api.get("/api/trading/positions");
    return extractResponseData(response);
  } catch (error) {
    return { data: null };
  }
};

// ============================================
// Positioning API Methods
// ============================================

export const getPositioningData = async (symbol, params = {}) => {
  try {
    const response = await api.get(`/api/positioning/stocks`, {
      params: { symbol, ...params },
    });
    return extractResponseData(response);
  } catch (error) {
    console.error(`Error fetching positioning data for ${symbol}:`, error);
    return { data: null };
  }
};

export const getPositioningSummary = async () => {
  try {
    const response = await api.get("/api/positioning/summary");
    return extractResponseData(response);
  } catch (error) {
    return { data: null };
  }
};

export const getTopPositioningMovers = async (limit = 20) => {
  try {
    const response = await api.get("/api/positioning/data", {
      params: { limit },
    });
    return extractResponseData(response);
  } catch (error) {
    return { data: null };
  }
};

// Trade endpoints consolidated:
// GET /api/trades - Get all trades with filtering/pagination (symbol, type, source, page, limit, sort)
// GET /api/trades/summary - Get trade summary statistics
// See TradeHistory.jsx which calls these endpoints directly

// ==============================================================
// All functions are exported via named exports above.
// This split was necessary because the monolithic 4367-line file
// was causing memory issues during build. By splitting at line 1637,
// we reduced each file to ~2000-2700 lines, which resolves the issue.
// All 29 files that import from this module continue to work unchanged.
// ==============================================================

// Export api as default for backwards compatibility
export default api;
