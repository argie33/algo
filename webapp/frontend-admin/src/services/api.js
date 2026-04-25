import axios from "axios";

// Debug logging - disable in production by setting to false
const DEBUG_API = import.meta.env.DEV || typeof window !== "undefined" && window.__DEBUG_API__;

// Helper to reduce console spam in production
const debugLog = (...args) => DEBUG_API && console.log(...args);
const debugWarn = (...args) => DEBUG_API && console.warn(...args);
const debugError = (...args) => {
  console.error(...args);
};

// ============================================================================
// GET API CONFIGURATION
// ============================================================================
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
    apiUrl = "/";
  } else if (!apiUrl && typeof window !== "undefined") {
    console.error(
      "❌ CRITICAL: API_URL not configured. Set VITE_API_URL env var or window.__CONFIG__.API_URL at build time"
    );
    apiUrl = "/";
  }

  if (!isDev && apiUrl === "/") {
    console.warn("⚠️ API_URL is relative path in production - this may cause failures");
  }

  debugLog("🔧 [API CONFIG]", {
    finalApiUrl: apiUrl,
    isDev: isDev,
  });

  const isTestEnv = typeof process !== "undefined" && process.env.NODE_ENV === "test";
  const isDevelopment = isTestEnv ? true : !!(import.meta.env && import.meta.env.DEV);
  const isProduction = isTestEnv ? false : !!(import.meta.env && import.meta.env.PROD);

  return {
    baseURL: apiUrl,
    isServerless: !!apiUrl && !apiUrl.includes("localhost"),
    apiUrl: apiUrl,
    isConfigured: !!apiUrl && !apiUrl.includes("localhost"),
    isDevelopment: isDevelopment,
    isProduction: isProduction,
  };
};

// Create API instance
let currentConfig = getApiConfig();

let api = axios.create({
  baseURL: currentConfig.baseURL,
  timeout: currentConfig.isServerless ? 45000 : 30000,
  headers: {
    "Content-Type": "application/json",
  },
});

// Add request interceptor - add auth token if available
try {
  if (api && api.interceptors) {
    api.interceptors.request.use(
      (config) => {
        config.metadata = { startTime: new Date(), retryCount: 0 };

        // Add JWT token from localStorage if available
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
  }
} catch (error) {
  if (typeof process !== "undefined" && process.env.NODE_ENV === "test") {
    console.warn("[API] Request interceptor skipped in test environment");
  }
}

// Add response interceptor - error handling and retries
try {
  if (api && api.interceptors) {
    api.interceptors.response.use(
      (response) => {
        if (response.config.metadata) {
          const duration = new Date() - response.config.metadata.startTime;
          if (duration > 10000) {
            console.warn(`⚠️ Slow API request:`, {
              url: response.config.url,
              method: response.config.method,
              duration: `${duration}ms`,
            });
          }
        }
        return response;
      },
      async (error) => {
        // Retry logic for transient failures
        const retryCount = error.config?.metadata?.retryCount || 0;
        const maxRetries = 2;
        const isRetryable = (error.code === "ECONNABORTED" ||
                            error.code === "ERR_NETWORK" ||
                            error.response?.status >= 500);

        if (isRetryable && retryCount < maxRetries) {
          const delay = 1000 * Math.pow(2, retryCount);
          error.config.metadata.retryCount = retryCount + 1;
          await new Promise(r => setTimeout(r, delay));
          return api(error.config);
        }

        // User-friendly error messages
        let userMessage = "An unexpected error occurred";
        if (error.code === "ECONNABORTED") {
          userMessage = "Request timed out. The server may be experiencing high load. Please try again.";
        } else if (error.code === "ERR_NETWORK") {
          userMessage = "Network connection failed. Please check your internet connection.";
        } else if (error.response?.status === 401) {
          userMessage = "Authentication failed. Please sign in again.";
        } else if (error.response?.status === 403) {
          userMessage = "Access denied. You do not have permission for this resource.";
        } else if (error.response?.status === 404) {
          userMessage = "The requested resource was not found.";
        } else if (error.response?.status >= 500) {
          userMessage = "Server error occurred. Please try again later.";
        } else if (!navigator.onLine) {
          userMessage = "No internet connection. Please check your network.";
        }

        error.userMessage = userMessage;

        const logData = {
          url: error.config?.url,
          method: error.config?.method,
          status: error.response?.status,
          message: error.message,
          code: error.code,
        };

        if (error.response?.status >= 500) {
          console.error("❌ Server Error:", logData);
        } else if (error.response?.status >= 400) {
          console.warn("⚠️ Client Error:", logData);
        } else if (error.code) {
          console.error("❌ Network Error:", logData);
        }

        return Promise.reject(error);
      }
    );
  }
} catch (error) {
  if (typeof process !== "undefined" && process.env.NODE_ENV === "test") {
    console.warn("[API] Response interceptor skipped in test environment");
  }
}

export { api };

// ============================================================================
// RESPONSE DATA EXTRACTION HELPERS
// ============================================================================

// Extract data from API response - supports multiple response formats
export const extractResponseData = (response, fallbackArray = []) => {
  if (!response) return fallbackArray;

  const data = response.data || response;

  // Try to extract array-like data in order of precedence
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.data)) return data.data;
  if (Array.isArray(data?.items)) return data.items;
  if (Array.isArray(data?.results)) return data.results;

  return fallbackArray;
};

// Deprecated alias for backwards compatibility
export const extractDataFromResponse = extractResponseData;

// ============================================================================
// ERROR HANDLING HELPERS
// ============================================================================

export const handleApiError = (error, context = "API call") => {
  const errorMessage = error?.response?.data?.error || error?.message || "Unknown error";
  debugError(`❌ ${context} failed:`, errorMessage);
  return {
    success: false,
    error: errorMessage,
    userMessage: error?.userMessage || errorMessage,
  };
};

export const withErrorHandler = async (asyncFn, context = "API call") => {
  try {
    return await asyncFn();
  } catch (error) {
    return handleApiError(error, context);
  }
};

// ============================================================================
// PORTFOLIO API FUNCTIONS
// ============================================================================

export const getApiKeys = async (userId) => {
  try {
    const response = await api.get(`/api/portfolio/api-keys?userId=${userId}`);
    return {
      success: true,
      data: extractResponseData(response),
    };
  } catch (error) {
    return handleApiError(error, "fetch API keys");
  }
};

export const saveApiKey = async (userId, keyData) => {
  try {
    const response = await api.post(`/api/portfolio/api-keys`, { userId, ...keyData });
    return {
      success: true,
      data: response.data,
    };
  } catch (error) {
    return handleApiError(error, "save API key");
  }
};

export const deleteApiKey = async (keyId) => {
  try {
    const response = await api.delete(`/api/portfolio/api-keys/${keyId}`);
    return {
      success: true,
      data: response.data,
    };
  } catch (error) {
    return handleApiError(error, "delete API key");
  }
};

export const testApiKey = async (keyData) => {
  try {
    const response = await api.post(`/api/portfolio/test-api-key`, keyData);
    return {
      success: true,
      data: response.data,
    };
  } catch (error) {
    return handleApiError(error, "test API key");
  }
};

export const importPortfolioFromAlpaca = async () => {
  try {
    const response = await api.post(`/api/portfolio/import/alpaca`);
    return {
      success: true,
      data: response.data,
    };
  } catch (error) {
    return handleApiError(error, "import from Alpaca");
  }
};

export const syncPortfolioFromAllSources = async () => {
  try {
    const response = await api.post(`/api/portfolio/sync`);
    return {
      success: true,
      data: response.data,
    };
  } catch (error) {
    return handleApiError(error, "sync portfolio");
  }
};

// ============================================================================
// CONTACT/MESSAGES API FUNCTIONS
// ============================================================================

export const getContactSubmissions = async (page = 1, limit = 50) => {
  try {
    const response = await api.get(`/api/contact/submissions?page=${page}&limit=${limit}`);
    return {
      success: true,
      data: extractResponseData(response),
      pagination: response.data?.pagination,
    };
  } catch (error) {
    return handleApiError(error, "fetch contact submissions");
  }
};

export const updateContactSubmissionStatus = async (submissionId, status) => {
  try {
    const response = await api.post(
      `/api/contact/submissions/${submissionId}/status`,
      { status }
    );
    return {
      success: true,
      data: response.data,
    };
  } catch (error) {
    return handleApiError(error, "update submission status");
  }
};

// ============================================================================
// STOCKS API FUNCTIONS
// ============================================================================

export const getDeepValueStocks = async (limit = 5000, offset = 0) => {
  try {
    const response = await api.get(`/api/stocks/deep-value?limit=${limit}&offset=${offset}`);
    return {
      success: true,
      data: extractResponseData(response),
      pagination: response.data?.pagination,
    };
  } catch (error) {
    return handleApiError(error, "fetch deep value stocks");
  }
};

// ============================================================================
// SETTINGS API FUNCTIONS
// ============================================================================

export const updateSettings = async (settingsData) => {
  try {
    const response = await api.put(`/api/user/settings`, settingsData);
    return {
      success: true,
      data: response.data,
    };
  } catch (error) {
    return handleApiError(error, "update settings");
  }
};
