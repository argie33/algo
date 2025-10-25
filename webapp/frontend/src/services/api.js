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
    runtimeApiUrl ||
    (import.meta.env && import.meta.env.VITE_API_URL) ||
    "http://localhost:3002";

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
    apiHealthy = response.ok;
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

// Portfolio API functions
export const getPortfolioData = async () => {
  try {
    const response = await api.get("/api/portfolio/holdings");
    return response?.data || null;
  } catch (error) {
    console.error("Error fetching portfolio data:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    throw error;
  }
};

export const getPortfolioHoldings = async (userId) => {
  try {
    // Validate user ID
    if (!userId || typeof userId !== "string" || userId.trim() === "") {
      throw new Error("Invalid user ID");
    }

    const response = await api.get(`/api/portfolio/holdings?userId=${userId}`);
    return response?.data || null;
  } catch (error) {
    console.error("Error fetching portfolio holdings:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
      userId,
    });
    throw error;
  }
};

export const getRiskAssessment = async (userId) => {
  try {
    const response = await api.get(`/api/portfolio/risk?userId=${userId}`);
    return response?.data || null;
  } catch (error) {
    console.error("Error fetching risk assessment:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
      userId,
    });
    throw error;
  }
};

export const getFactorAnalysis = async (userId) => {
  try {
    const response = await api.get(`/api/portfolio/factors?userId=${userId}`);
    return response?.data || null;
  } catch (error) {
    console.error("Error fetching factor analysis:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
      userId,
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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    throw error;
  }
};

export const importPortfolioFromBroker = async (broker) => {
  try {
    const response = await api.post(`/portfolio/import/${broker}`);
    return response?.data;
  } catch (error) {
    console.error("Error importing portfolio from broker:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    throw error;
  }
};

export const getRiskAnalysis = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams();
    if (params.period) queryParams.append("period", params.period);
    if (params.confidence_level)
      queryParams.append("confidence_level", params.confidence_level);

    const response = await api.get(
      `/api/risk/analysis${queryParams.toString() ? "?" + queryParams.toString() : ""}`
    );
    return response?.data;
  } catch (error) {
    console.error("Error fetching risk analysis:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    throw error;
  }
};

export const getRiskDashboard = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams();
    if (params.period) queryParams.append("period", params.period);

    const response = await api.get(
      `/api/risk/dashboard${queryParams.toString() ? "?" + queryParams.toString() : ""}`
    );
    return response?.data;
  } catch (error) {
    console.error("Error fetching risk dashboard:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    throw error;
  }
};

export const getRiskAlerts = async () => {
  try {
    const response = await api.get("/api/risk/alerts");
    return response?.data;
  } catch (error) {
    console.error("Error fetching risk alerts:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    throw error;
  }
};

export const createRiskAlert = async (alertData) => {
  try {
    const response = await api.post("/api/risk/alerts", alertData);
    return response?.data;
  } catch (error) {
    console.error("Error creating risk alert:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    throw error;
  }
};

// API Keys management
export const getApiKeys = async () => {
  try {
    const response = await api.get("/portfolio/api-keys");

    // Convert array format to object format expected by frontend
    const apiKeysArray = response?.data?.data || [];
    const apiKeysObject = apiKeysArray.reduce((acc, apiKey) => {
      acc[apiKey.brokerName] = {
        ...apiKey,
        lastValidated: apiKey.lastUsed || apiKey.createdAt
      };
      return acc;
    }, {});

    // Add ok property to match fetch API behavior expected by frontend
    return {
      ok: response?.status >= 200 && response?.status < 300,
      status: response?.status,
      data: apiKeysObject,
      success: response?.data?.success || true
    };
  } catch (error) {
    console.error("Error fetching API keys:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    throw error;
  }
};

export const addApiKey = async (apiKeyData) => {
  try {
    const response = await api.post("/portfolio/api-keys", apiKeyData);
    return response?.data;
  } catch (error) {
    console.error("Error adding API key:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    throw error;
  }
};

export const updateApiKey = async (keyId, apiKeyData) => {
  try {
    const response = await api.put(`/portfolio/api-keys/${keyId}`, apiKeyData);
    return response?.data;
  } catch (error) {
    console.error("Error updating API key:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    throw error;
  }
};

export const deleteApiKey = async (keyId) => {
  try {
    const response = await api.delete(`/portfolio/api-keys/${keyId}`);
    return response?.data;
  } catch (error) {
    console.error("Error deleting API key:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    throw error;
  }
};

// Alias for tests - saveApiKey is equivalent to addApiKey
export const saveApiKey = async (apiKeyData) => {
  try {
    const response = await api.post("/portfolio/api-keys", apiKeyData);
    return { ok: true, data: response?.data };
  } catch (error) {
    console.error("Error saving API key:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    throw new Error(error.message);
  }
};

// Test API key functionality
export const testApiKey = async (apiKeyData) => {
  try {
    const response = await api.post("/portfolio/test-api-key", apiKeyData);
    return { ok: true, isValid: response?.data?.isValid, data: response?.data };
  } catch (error) {
    console.error("Error testing API key:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    throw new Error(error.message);
  }
};

// User settings functions
export const getSettings = async () => {
  try {
    const response = await api.get("/api/settings");
    return response?.data;
  } catch (error) {
    console.error("Error getting settings:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    throw error;
  }
};

export const updateSettings = async (settings) => {
  try {
    const response = await api.post("/api/settings", settings);
    return { ok: true, success: true, data: response?.data };
  } catch (error) {
    console.error("Error updating settings:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    throw new Error(error.message);
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
    // Always return { data: ... } structure for consistency
    const result = normalizeApiResponse(response, false);
    console.log("📈 [API] Market overview normalized result:", result);
    return { data: result };
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

    throw new Error(handleApiError(error, "Failed to fetch market overview"));
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
    const result = normalizeApiResponse(response, false);
    console.log("📈 [API] Top stocks normalized result:", result);
    return { data: result };
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
    throw new Error(handleApiError(error, "Failed to fetch top stocks"));
  }
};

export const getStockScores = async (symbol, params = {}) => {
  console.log(`📈 [API] Fetching scores for ${symbol}...`, params);
  console.log("📈 [API] Current config:", getApiConfig());

  try {
    const queryParams = new URLSearchParams({
      symbol: symbol,
      limit: params.limit || 20,
      ...params,
    }).toString();

    const endpoint = `/api/scores/latest?${queryParams}`;

    console.log(`📈 [API] Trying scores endpoint: ${endpoint}`);
    const response = await api.get(endpoint);
    console.log(`📈 [API] SUCCESS with scores endpoint: ${endpoint}`, response);

    const result = normalizeApiResponse(response, true);

    // Filter for the specific symbol if provided
    if (symbol && result?.length > 0) {
      const symbolScores = result.filter(score => score.symbol === symbol);
      return { data: symbolScores.length > 0 ? symbolScores[0] : null };
    }

    return { data: result };
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
    throw new Error(handleApiError(error, `Failed to fetch scores for ${symbol}`));
  }
};

export const getMarketSentimentHistory = async (days = 30) => {
  console.log(`📊 [API] Fetching market sentiment history for ${days} days...`);

  try {
    const response = await api.get(
      `/api/market/sentiment/history?days=${days}`
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
    throw new Error(errorMessage);
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
    throw new Error(errorMessage);
  }
};

export const getMarketBreadth = async () => {
  console.log(`📊 [API] Fetching market breadth...`);

  try {
    const response = await api.get(`/api/market/breadth`);
    console.log(`📊 [API] Fetched market breadth:`, response.data);

    // Always return { data: ... } structure for consistency
    if (response?.data && typeof response?.data === "object") {
      console.log("📊 [API] Returning breadth data structure:", response?.data);
      return response?.data;
    }

    // Fallback to normalized response
    const result = normalizeApiResponse(response, false);
    console.log("📊 [API] Breadth fallback normalized result:", result);
    return { data: result };
  } catch (error) {
    console.error("❌ [API] Market breadth error details:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
      url: error.config?.url,
      method: error.config?.method,
    });
    const errorMessage = handleApiError(error, "get market breadth");
    throw new Error(errorMessage);
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
    const result = normalizeApiResponse(response, false);
    console.log("📊 [API] Internals fallback normalized result:", result);
    return { data: result };
  } catch (error) {
    console.error("❌ [API] Market internals error details:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
      url: error.config?.url,
      method: error.config?.method,
    });
    const errorMessage = handleApiError(error, "get market internals");
    throw new Error(errorMessage);
  }
};

export const getDistributionDays = async () => {
  console.log(`📊 [API] Fetching distribution days...`);

  try {
    const endpoints = [`/api/market/distribution-days`, `/market/distribution-days`];
    let response = null;
    let lastError = null;

    for (const endpoint of endpoints) {
      try {
        console.log(`📊 [API] Trying distribution days endpoint: ${endpoint}`);
        response = await api.get(endpoint);
        console.log(`📊 [API] SUCCESS with distribution days endpoint: ${endpoint}`, response);
        break;
      } catch (err) {
        console.log(`📊 [API] FAILED distribution days endpoint: ${endpoint}`, err.message);
        lastError = err;
        continue;
      }
    }

    if (!response) {
      console.error("📊 [API] All distribution days endpoints failed:", {
        message: lastError?.message || "Unknown error",
        status: lastError.response?.status,
        url: lastError.config?.url,
      });
      throw lastError;
    }

    if (response?.data && typeof response?.data === "object") {
      console.log("📊 [API] Returning distribution days data structure:", response?.data);
      return response?.data;
    }

    const result = normalizeApiResponse(response, false);
    console.log("📊 [API] Distribution days fallback normalized result:", result);
    return { data: result };
  } catch (error) {
    console.error("❌ [API] Distribution days error details:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
      url: error.config?.url,
      method: error.config?.method,
    });
    const errorMessage = handleApiError(error, "get distribution days");
    throw new Error(errorMessage);
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
    const result = normalizeApiResponse(response, true);
    console.log("📊 [API] Economic fallback normalized result:", result);
    return { data: result };
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
      success: response.success,
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
    const result = normalizeApiResponse(response, true);
    console.log("📅 [API] Seasonality fallback normalized result:", result);
    return { data: result };
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

    if (response?.data?.data?.yield_curve) {
      console.log("📈 [API] Fetched yield curve data:", response.data.data.yield_curve);
      return {
        success: true,
        data: response.data.data.yield_curve,
        timestamp: new Date().toISOString()
      };
    }

    throw new Error("Yield curve data not available");
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
    return response.data;
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
    const response = await api.get("/api/market/sentiment-divergence");
    console.log("💡 [API] Fetched sentiment divergence:", response.data);
    return response.data;
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
    const result = normalizeApiResponse(response, true);
    console.log(
      "🔬 [API] Research indicators fallback normalized result:",
      result
    );
    return { data: result };
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

export const getPortfolioAnalytics = async (timeframe = "1y") => {
  console.log("📈 [API] Fetching portfolio analytics...");

  try {
    const endpoints = [`/api/portfolio/analytics?timeframe=${timeframe}`];

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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
      url: error.config?.url,
      method: error.config?.method,
      stack: error?.stack?.substring(0, 500) + "...",
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
    const endpoints = [`/api/portfolio/risk-analysis`];

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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
      url: error.config?.url,
      method: error.config?.method,
      stack: error?.stack?.substring(0, 500) + "...",
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
    const endpoints = [`/api/portfolio/optimization`];

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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
      url: error.config?.url,
      method: error.config?.method,
      stack: error?.stack?.substring(0, 500) + "...",
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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
      url: error.config?.url,
      method: error.config?.method,
      stack: error?.stack?.substring(0, 500) + "...",
    });
    const errorMessage = handleApiError(error, "get stocks");
    throw new Error(errorMessage);
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
    throw new Error(errorMessage);
  }
};

// Chunked stocks loading
export const getStocksChunk = async (chunkIndex = 0) => {
  try {
    const response = await api.get(`/api/stocks/chunk/${chunkIndex}`);
    return normalizeApiResponse(response);
  } catch (error) {
    const errorMessage = handleApiError(error, "get stocks chunk");
    throw new Error(errorMessage);
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
    throw new Error(errorMessage);
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
    const result = normalizeApiResponse(response, false); // Single stock is an object
    console.log("✅ getStock: returning result:", result);
    return { data: result };
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
    throw new Error(errorMessage);
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
    throw new Error(errorMessage);
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
    const result = normalizeApiResponse(response, true);
    console.log("✅ getStockFinancials: returning result:", result);
    return { data: result };
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
    throw new Error(errorMessage);
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
    throw new Error(errorMessage);
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
    throw new Error(errorMessage);
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
    throw new Error(errorMessage);
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
    throw new Error(errorMessage);
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
    throw new Error(errorMessage);
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
    throw new Error(errorMessage);
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
    throw new Error(errorMessage);
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
    throw new Error(errorMessage);
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
    throw new Error(errorMessage);
  }
};

// New method for stock screening with proper parameter handling
export const screenStocks = async (params) => {
  try {
    // Use /api/scores endpoint for complete stock data (5,277 stocks)
    // /api/stocks only has 116 records with financial metrics, causing "N/A" display
    const endpoint = "/api/scores";

    console.log("🔍 [API] Screening stocks with params:", params.toString());
    console.log(
      `🔍 [API] Using scores endpoint for complete data: ${endpoint}?${params.toString()}`
    );

    const response = await api.get(`${endpoint}?${params.toString()}`, {
      baseURL: currentConfig.baseURL,
    });

    console.log(`✅ [API] Success with scores endpoint:`, response?.data);

    // Backend returns: { success: true, data: { stocks: [...] }, total: ..., pagination: {...} }
    // or { success: true, data: [...], total: ..., pagination: {...} }
    if (response?.data && response?.data.success) {
      const dataField = response?.data.data;
      // Check if it's directly an array or if it has a stocks property
      if (Array.isArray(dataField) || (dataField && Array.isArray(dataField.stocks))) {
        console.log("✅ [API] Using backend response structure:", response?.data);
        return response?.data;
      }
    }

    // Fallback to normalized response
    const result = normalizeApiResponse(response, true);
    console.log("✅ [API] Using normalized response:", result);
    return {
      success: true,
      data: result,
      total: result?.length || 0,
      pagination: {
        total: result?.length || 0,
        page: 1,
        limit: result?.length || 0,
      },
    };
  } catch (error) {
    console.error("❌ [API] Error screening stocks:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
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
    const response = await api.get('/api/signals/buy');
    return response.data;
  } catch (error) {
    console.error("❌ [API] Buy signals error:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    return { data: null };
  }
};

export const getSellSignals = async () => {
  console.log("📉 [API] Fetching sell signals...");
  try {
    const response = await api.get('/api/signals/sell');
    return response.data;
  } catch (error) {
    console.error("❌ [API] Sell signals error:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
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
    throw new Error(errorMessage);
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
    throw new Error(errorMessage);
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
    throw new Error(errorMessage);
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
    throw new Error(errorMessage);
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
    throw new Error(errorMessage);
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
    throw new Error(errorMessage);
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
    throw new Error(errorMessage);
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
    throw new Error(errorMessage);
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
    throw new Error(errorMessage);
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
    throw new Error(errorMessage);
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
    throw new Error(errorMessage);
  }
};

export const getIncomeStatement = async (ticker, period = "annual") => {
  try {
    const response = await api.get(
      `/api/financials/${ticker}/income-statement?period=${period}`
    );
    const result = normalizeApiResponse(response, true);

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

    return { data: transformedData };
  } catch (error) {
    const errorMessage = handleApiError(error, "get income statement");
    throw new Error(errorMessage);
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
    throw new Error(errorMessage);
  }
};

export const getBalanceSheet = async (ticker, period = "annual") => {
  try {
    const response = await api.get(
      `/api/financials/${ticker}/balance-sheet?period=${period}`
    );
    const result = normalizeApiResponse(response, true);

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

    return { data: transformedData };
  } catch (error) {
    const errorMessage = handleApiError(error, "get balance sheet");
    throw new Error(errorMessage);
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
    throw new Error(errorMessage);
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
    throw new Error(errorMessage);
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
    throw new Error(errorMessage);
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
    throw new Error(errorMessage);
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
    throw new Error(errorMessage);
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
    throw new Error(errorMessage);
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
    throw new Error(errorMessage);
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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
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
    throw new Error(errorMessage);
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
    throw new Error(errorMessage);
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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
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
    throw new Error(errorMessage);
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
    throw new Error(errorMessage);
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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
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
    throw new Error(errorMessage);
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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
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
      status: response?.status,
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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      url: error.config?.url,
    });
    const errorMessage = handleApiError(error, "get market indices");
    throw new Error(errorMessage);
  }
};

// Sector performance
export const getSectorPerformance = async () => {
  console.log("🚀 getSectorPerformance: Starting API call...");
  try {
    const response = await api.get("/api/sectors/sectors-with-history");

    console.log("📊 getSectorPerformance: Raw response:", {
      status: response?.status,
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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      url: error.config?.url,
    });
    const errorMessage = handleApiError(error, "get sector performance");
    throw new Error(errorMessage);
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
    const result = normalizeApiResponse(response, true);
    console.log("✅ getMarketVolatility: returning result:", result);
    return { data: result };
  } catch (error) {
    console.error("❌ Error fetching market volatility:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    const errorMessage = handleApiError(error, "get market volatility");
    throw new Error(errorMessage);
  }
};

// Economic calendar
export const getEconomicCalendar = async () => {
  console.log("🚀 getEconomicCalendar: Starting API call...");
  try {
    const response = await api.get("/api/market/calendar");

    console.log("📊 getEconomicCalendar: Raw response:", {
      status: response?.status,
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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    const errorMessage = handleApiError(error, "get economic calendar");
    throw new Error(errorMessage);
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
    const result = normalizeApiResponse(response, true);
    console.log("✅ getMarketCapCategories: returning result:", result);
    return { data: result };
  } catch (error) {
    console.error("❌ Error fetching market cap categories:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    const errorMessage = handleApiError(error, "get market cap categories");
    throw new Error(errorMessage);
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
      status: response?.status,
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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    const errorMessage = handleApiError(error, "get technical indicators");
    throw new Error(errorMessage);
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
      status: response?.status,
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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    const errorMessage = handleApiError(error, "get volume data");
    throw new Error(errorMessage);
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
      status: response?.status,
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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    const errorMessage = handleApiError(error, "get support resistance levels");
    throw new Error(errorMessage);
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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      url: error.config?.url,
    });
    throw new Error(handleApiError(error, "Failed to fetch market indicators"));
  }
};

export const getMarketSentiment = async () => {
  console.log("😊 [API] Fetching market sentiment...");
  try {
    const response = await api.get('/api/sentiment/market');
    return response.data;
  } catch (error) {
    console.error("❌ [API] Market sentiment error:", {
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
    const result = normalizeApiResponse(response, false);
    return { data: result };
  } catch (error) {
    console.error(`❌ [API] Financial data error for ${symbol}:`, {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      url: error.config?.url,
      symbol,
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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
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
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
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
    const response = await api.get('/api/user/profile');
    return response.data;
  } catch (error) {
    console.error("❌ [API] Dashboard user error:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    return { data: null };
  }
};

export const getDashboardWatchlist = async () => {
  console.log("👀 [API] Fetching dashboard watchlist...");
  try {
    // Try to get real watchlist data from backend
    try {
      const response = await api.get("/api/watchlist");
      if (response.data && response.data.success && response.data.data) {
        console.log("✅ [API] Real watchlist data loaded");
        return response.data;
      }
    } catch (watchlistError) {
      console.warn("⚠️ [API] Watchlist endpoint failed, trying stocks list");
    }

    // Fallback: get a subset of stocks from the main stocks API
    try {
      const stocksResponse = await api.get("/api/stocks?limit=5");
      if (
        stocksResponse.data &&
        stocksResponse.data.success &&
        stocksResponse.data.data
      ) {
        const watchlistData = stocksResponse.data.data.map((stock) => ({
          symbol: stock.symbol,
          name: stock.security_name || stock.symbol,
          price: stock.price?.current || 0,
          change: stock.price?.current ? stock.price.current * 0.01 : 0, // Approximate
          changePercent: stock.price?.current ? 1.0 : 0, // Approximate
        }));
        console.log(
          "✅ [API] Watchlist created from stocks data:",
          watchlistData.length,
          "items"
        );
        return { data: watchlistData, success: true };
      }
    } catch (stocksError) {
      console.warn("⚠️ [API] Stocks endpoint failed:", stocksError.message);
    }

    // If all else fails, show a helpful error instead of mock data
    throw new Error(
      "Unable to load watchlist. Please ensure the backend services are running and accessible."
    );
  } catch (error) {
    console.error("❌ [API] Dashboard watchlist error:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    throw new Error(
      handleApiError(error, "Failed to fetch dashboard watchlist")
    );
  }
};

export const getDashboardPortfolio = async () => {
  console.log("💼 [API] Fetching dashboard portfolio...");
  try {
    // Call real API endpoint
    const response = await api.get('/api/portfolio/dashboard');
    console.log("💼 [API] Dashboard portfolio response:", response.data);
    return response.data;
  } catch (error) {
    console.error("❌ [API] Dashboard portfolio error:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    // Return empty data instead of mock fallback
    return { data: null };
  }
};

export const getDashboardPortfolioMetrics = async () => {
  console.log("📊 [API] Fetching dashboard portfolio metrics...");
  try {
    const response = await api.get('/api/portfolio/metrics');
    return response.data;
  } catch (error) {
    console.error("❌ [API] Dashboard portfolio metrics error:", {
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
    return response.data;
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
    return response.data;
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
    return response.data;
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
    return response.data;
  } catch (error) {
    console.error("❌ [API] Dashboard earnings calendar error:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    throw new Error(
      handleApiError(error, "Failed to fetch dashboard earnings calendar")
    );
  }
};

export const getDashboardFinancialHighlights = async () => {
  console.log("💰 [API] Fetching dashboard financial highlights...");
  try {
    const response = await api.get("/api/financials/highlights");
    console.log("💰 [API] Financial highlights response:", response.data);
    return response.data;
  } catch (error) {
    console.error("❌ [API] Dashboard financial highlights error:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    throw new Error(
      handleApiError(error, "Failed to fetch dashboard financial highlights")
    );
  }
};

export const getDashboardSymbols = async () => {
  console.log("🔤 [API] Fetching dashboard symbols...");
  try {
    const response = await api.get("/api/dashboard/symbols");
    console.log("🔤 [API] Dashboard symbols response:", response.data);
    return response.data;
  } catch (error) {
    console.error("❌ [API] Dashboard symbols error:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
    });
    throw new Error(handleApiError(error, "Failed to fetch dashboard symbols"));
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

    const endpoint = `/api/signals?${queryParams}`;
    console.log(`📈 [API] Using endpoint: ${endpoint}`);
    const response = await api.get(endpoint);
    console.log(`📈 [API] SUCCESS with endpoint: ${endpoint}`, response);

    console.log("📈 [API] Trading signals daily raw response:", response);
    const result = normalizeApiResponse(response, false);
    console.log("📈 [API] Trading signals daily normalized result:", result);
    return { data: result };
  } catch (error) {
    console.error("❌ [API] Trading signals daily error details:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
      url: error.config?.url,
      method: error.config?.method,
      stack: error?.stack?.substring(0, 500) + "...",
    });
    throw new Error(
      handleApiError(error, "Failed to fetch daily trading signals")
    );
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
    const result = normalizeApiResponse(response, false);
    console.log("👤 [API] Current user normalized result:", result);
    return { data: result };
  } catch (error) {
    console.error("❌ [API] Current user error details:", {
      message: error?.message || "Unknown error",
      status: error.response?.status,
      statusText: error.response?.statusText,
      url: error.config?.url,
      method: error.config?.method,
      stack: error?.stack?.substring(0, 500) + "...",
    });
    throw new Error(handleApiError(error, "Failed to fetch current user"));
  }
};

export const getDashboardTechnicalSignals = async () => {
  console.log("📊 [API] Fetching dashboard technical signals...");
  try {
    const response = await api.get('/api/signals/dashboard');
    return response.data;
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
    throw new Error(
      `Failed to fetch quote for ${symbol}: ${error?.message || "Unknown error"}`
    );
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
    throw new Error(
      `Failed to place order: ${error?.message || "Unknown error"}`
    );
  }
};

// AI Chat functions for EnhancedAIChat component
export const sendChatMessage = async (message, options = {}) => {
  try {
    const response = await api.post("/api/ai/chat", {
      message,
      ...options,
    });
    return response?.data;
  } catch (error) {
    console.error("Failed to send chat message:", error);
    throw new Error(handleApiError(error, "Failed to send chat message"));
  }
};

export const clearChatHistory = async () => {
  try {
    const response = await api.delete("/api/ai/chat/history");
    return response?.data;
  } catch (error) {
    console.error("Failed to clear chat history:", error);
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
  getMarketCorrelation,
  getSeasonalityData,
  getYieldCurveData,
  getMcClellanOscillator,
  getSentimentDivergence,
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
  getRiskDashboard,
  getRiskAlerts,
  createRiskAlert,
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
  saveApiKey,
  testApiKey,

  // User Settings
  getSettings,
  updateSettings,

  // Trading functions
  placeOrder,
  getQuote,
  getTradingSignalsDaily,

  // AI Chat functions
  sendChatMessage,
  clearChatHistory,

  // Generic HTTP methods for direct API calls - test-safe
  get: (url, config) => {
    // In test environment, use mocked axios directly if api is null
    if (
      !api &&
      typeof process !== "undefined" &&
      process.env.NODE_ENV === "test"
    ) {
      return axios.get(url, config);
    }
    return api?.get(url, config) || Promise.resolve({ data: {} });
  },
  post: (url, data, config) => {
    if (
      !api &&
      typeof process !== "undefined" &&
      process.env.NODE_ENV === "test"
    ) {
      return axios.post(url, data, config);
    }
    return api?.post(url, data, config) || Promise.resolve({ data: {} });
  },
  put: (url, data, config) => {
    if (
      !api &&
      typeof process !== "undefined" &&
      process.env.NODE_ENV === "test"
    ) {
      return axios.put(url, data, config);
    }
    return api?.put(url, data, config) || Promise.resolve({ data: {} });
  },
  delete: (url, config) => {
    if (
      !api &&
      typeof process !== "undefined" &&
      process.env.NODE_ENV === "test"
    ) {
      return axios.delete(url, config);
    }
    return api?.delete(url, config) || Promise.resolve({ data: {} });
  },
  patch: (url, data, config) => {
    if (
      !api &&
      typeof process !== "undefined" &&
      process.env.NODE_ENV === "test"
    ) {
      return axios.patch(url, data, config);
    }
    return api?.patch(url, data, config) || Promise.resolve({ data: {} });
  },
};

// Add aliases for test compatibility - fetchXxx functions expected by tests
export const fetchPortfolioHoldings = getPortfolioHoldings;
export const fetchMarketOverview = getMarketOverview;
export const fetchStockData = getStock;
export const fetchTechnicalData = getTechnicalIndicators;
export const fetchPortfolioPerformance = getPortfolioPerformance;
export const fetchMarketData = getMarketIndicators;
export const fetchEarningsData = getEarningsData;
export const fetchHistoricalData = getStockHistory;

// Advanced Analytics API functions
export const getAnalyticsOverview = async () => {
  try {
    const response = await api.get("/api/analytics/overview");
    return response.data;
  } catch (error) {
    console.error("Error fetching analytics overview:", error);
    throw new Error(
      handleApiError(error, "Failed to fetch analytics overview")
    );
  }
};

export const getPerformanceAnalytics = async (
  period = "1m",
  benchmark = "SPY"
) => {
  try {
    const response = await api.get("/api/analytics/performance", {
      params: { period, benchmark },
    });
    return response.data;
  } catch (error) {
    console.error("Error fetching performance analytics:", error);
    throw new Error(
      handleApiError(error, "Failed to fetch performance analytics")
    );
  }
};

export const getRiskAnalytics = async (timeframe = "1m") => {
  try {
    const response = await api.get("/api/analytics/risk", {
      params: { timeframe },
    });
    return response.data;
  } catch (error) {
    console.error("Error fetching risk analytics:", error);
    throw new Error(handleApiError(error, "Failed to fetch risk analytics"));
  }
};

export const getCorrelationAnalytics = async (
  period = "3m",
  assets = "all"
) => {
  try {
    const response = await api.get("/api/analytics/correlation", {
      params: { period, assets },
    });
    return response.data;
  } catch (error) {
    console.error("Error fetching correlation analytics:", error);
    throw new Error(
      handleApiError(error, "Failed to fetch correlation analytics")
    );
  }
};

export const getAllocationAnalytics = async (period = "current") => {
  try {
    const response = await api.get("/api/analytics/allocation", {
      params: { period },
    });
    return response.data;
  } catch (error) {
    console.error("Error fetching allocation analytics:", error);
    throw new Error(
      handleApiError(error, "Failed to fetch allocation analytics")
    );
  }
};

export const getReturnsAnalytics = async (period = "1m") => {
  try {
    const response = await api.get("/api/analytics/returns", {
      params: { period },
    });
    return response.data;
  } catch (error) {
    console.error("Error fetching returns analytics:", error);
    throw new Error(handleApiError(error, "Failed to fetch returns analytics"));
  }
};

export const getSectorsAnalytics = async () => {
  try {
    const response = await api.get("/api/analytics/sectors");
    return response.data;
  } catch (error) {
    console.error("Error fetching sectors analytics:", error);
    throw new Error(handleApiError(error, "Failed to fetch sectors analytics"));
  }
};

export const getVolatilityAnalytics = async (period = "1m") => {
  try {
    const response = await api.get("/api/analytics/volatility", {
      params: { period },
    });
    return response.data;
  } catch (error) {
    console.error("Error fetching volatility analytics:", error);
    throw new Error(
      handleApiError(error, "Failed to fetch volatility analytics")
    );
  }
};

export const getTrendsAnalytics = async (period = "1m") => {
  try {
    const response = await api.get("/api/analytics/trends", {
      params: { period },
    });
    return response.data;
  } catch (error) {
    console.error("Error fetching trends analytics:", error);
    throw new Error(handleApiError(error, "Failed to fetch trends analytics"));
  }
};

// Portfolio Sector & Industry Analysis
export const getPortfolioSectorIndustryAnalysis = async () => {
  try {
    const response = await api.get("/api/portfolio/sector-industry-analysis");
    return response.data;
  } catch (error) {
    console.error("Error fetching portfolio sector/industry analysis:", error);
    throw new Error(handleApiError(error, "Failed to fetch sector/industry analysis"));
  }
};

// Professional Metrics (Alpha, Sortino, Information Ratio, etc.)
export const getProfessionalMetrics = async (timeframe = "1y", benchmark = "SPY") => {
  try {
    const response = await api.get("/api/analytics/professional-metrics", {
      params: { timeframe, benchmark },
    });
    return response.data;
  } catch (error) {
    console.error("Error fetching professional metrics:", error);
    throw new Error(handleApiError(error, "Failed to fetch professional metrics"));
  }
};

export const getCustomAnalytics = async (
  analysisType,
  parameters = {},
  symbols = []
) => {
  try {
    const response = await api.post("/api/analytics/custom", {
      analysis_type: analysisType,
      parameters,
      symbols,
    });
    return response.data;
  } catch (error) {
    console.error("Error fetching custom analytics:", error);
    throw new Error(handleApiError(error, "Failed to fetch custom analytics"));
  }
};

export const exportAnalytics = async (
  format = "json",
  report = "performance"
) => {
  try {
    const response = await api.get("/api/analytics/export", {
      params: { format, report },
    });
    return response.data;
  } catch (error) {
    console.error("Error exporting analytics:", error);
    throw new Error(handleApiError(error, "Failed to export analytics"));
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
    return response.data;
  } catch (error) {
    console.error("Error fetching market commentary:", error);
    throw new Error(handleApiError(error, "Failed to fetch market commentary"));
  }
};

export const getMarketTrends = async (period = "week") => {
  try {
    const response = await api.get("/api/research/trends", {
      params: { period },
    });
    return response.data;
  } catch (error) {
    console.error("Error fetching market trends:", error);
    throw new Error(handleApiError(error, "Failed to fetch market trends"));
  }
};

export const getAnalystOpinions = async () => {
  try {
    const response = await api.get("/api/research/analysts");
    return response.data;
  } catch (error) {
    console.error("Error fetching analyst opinions:", error);
    throw new Error(handleApiError(error, "Failed to fetch analyst opinions"));
  }
};

export const subscribeToCommentary = async (category = "all") => {
  try {
    const response = await api.post("/api/research/commentary/subscribe", {
      category,
    });
    return response.data;
  } catch (error) {
    console.error("Error subscribing to commentary:", error);
    throw new Error(handleApiError(error, "Failed to subscribe to commentary"));
  }
};

export const getOrderBook = async (symbol) => {
  try {
    const response = await api.get(`/api/trading/orderbook/${symbol}`);
    return response.data;
  } catch (error) {
    console.error("Error fetching order book:", error);
    throw new Error(handleApiError(error, "Failed to fetch order book"));
  }
};

export const getTradingPositions = async () => {
  try {
    const response = await api.get("/api/trading/positions");
    return response.data;
  } catch (error) {
    console.error("Error fetching trading positions:", error);
    throw new Error(handleApiError(error, "Failed to fetch trading positions"));
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
    return response.data;
  } catch (error) {
    console.error(`Error fetching positioning data for ${symbol}:`, error);
    throw new Error(handleApiError(error, "Failed to fetch positioning data"));
  }
};

export const getPositioningSummary = async () => {
  try {
    const response = await api.get("/api/positioning/summary");
    return response.data;
  } catch (error) {
    console.error("Error fetching positioning summary:", error);
    throw new Error(handleApiError(error, "Failed to fetch positioning summary"));
  }
};

export const getTopPositioningMovers = async (limit = 20) => {
  try {
    const response = await api.get("/api/positioning/data", {
      params: { limit },
    });
    return response.data;
  } catch (error) {
    console.error("Error fetching top positioning movers:", error);
    throw new Error(handleApiError(error, "Failed to fetch positioning movers"));
  }
};
