// Standardized API Service with consistent error handling and logging
import React from "react";

// Get API configuration - duplicated here to avoid circular dependency
const getApiConfig = () => {
  // Dynamic API URL resolution: runtime > build-time > fallback
  let runtimeApiUrl =
    typeof window !== "undefined" &&
    window.__CONFIG__ &&
    window.__CONFIG__.API_URL
      ? window.__CONFIG__.API_URL
      : null;
  const apiUrl =
    runtimeApiUrl || import.meta.env.VITE_API_URL || "http://localhost:3001";

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

// Enhanced logging utility
export const createLogger = (componentName) => ({
  info: (message, data) => {
    // Safe data handling for info to avoid circular references
    let safeData;
    try {
      safeData =
        data && typeof data === "object"
          ? JSON.parse(JSON.stringify(data))
          : data;
    } catch (error) {
      safeData = data
        ? String(data)
        : "Unable to stringify data (circular reference)";
    }
    if (import.meta.env && import.meta.env.DEV) {
      console.log(`[${componentName}] ${message}`, safeData);
    }
  },
  error: (message, error, context) => {
    // Safe error object to avoid circular references
    const safeErrorData = {
      errorMessage: error?.message || String(error || "Unknown error"),
      errorName: error?.name,
      errorCode: error?.code,
      isAxiosError: error?.isAxiosError,
      status: error?.response?.status,
      statusText: error?.response?.statusText,
      stack:
        error?.stack?.substring(0, 200) +
        (error?.stack?.length > 200 ? "..." : ""),
      timestamp: new Date().toISOString(),
      component: componentName,
      // Safe context without potential circular refs
      contextUrl: context?.url,
      contextStatus: context?.status,
      contextMethod: context?.method,
    };
    console.error(`[${componentName}] ${message}`, safeErrorData);
  },
  warn: (message, data) => {
    // Safe data handling for warn to avoid circular references
    let safeData;
    try {
      safeData =
        data && typeof data === "object"
          ? JSON.parse(JSON.stringify(data))
          : data;
    } catch (error) {
      safeData = data
        ? String(data)
        : "Unable to stringify data (circular reference)";
    }
    if (import.meta.env && import.meta.env.DEV) {
      console.warn(`[${componentName}] ${message}`, safeData);
    }
  },
  debug: (message, data) => {
    if (process.env.NODE_ENV === "development") {
      // Safe data handling for debug to avoid circular references
      let safeData;
      try {
        safeData =
          data && typeof data === "object"
            ? JSON.parse(JSON.stringify(data))
            : data;
      } catch (error) {
        safeData = data
          ? String(data)
          : "Unable to stringify data (circular reference)";
      }
      console.debug(`[${componentName}] ${message}`, safeData);
    }
  },
});

// Get stored auth token for API requests
const getAuthToken = () => {
  try {
    // Check for dev auth session
    const devSession = localStorage.getItem("dev_session");
    if (devSession) {
      const session = JSON.parse(devSession);
      if (
        session &&
        session.tokens &&
        session.tokens.accessToken &&
        Date.now() < session.expiresAt
      ) {
        return session.tokens.accessToken;
      }
    }

    // Fallback: check for dev-bypass-token
    if (
      window.location.hostname === "localhost" ||
      window.location.hostname === "127.0.0.1"
    ) {
      return "dev-bypass-token";
    }
  } catch (error) {
    // Silent failure for auth token retrieval
  }
  return null;
};

// Standardized fetch wrapper with enhanced error handling
export const apiCall = async (
  endpoint,
  options = {},
  componentName = "API"
) => {
  const { apiUrl: API_BASE } = getApiConfig();
  const logger = createLogger(componentName);

  const url = endpoint.startsWith("http") ? endpoint : `${API_BASE}${endpoint}`;
  const startTime = Date.now();

  // Get auth token and add to headers
  const authToken = getAuthToken();
  const authHeaders = authToken ? { Authorization: `Bearer ${authToken}` } : {};

  const requestOptions = {
    headers: {
      "Content-Type": "application/json",
      ...authHeaders,
      ...options.headers,
    },
    ...options,
  };

  logger.info("Making API request", {
    url,
    method: requestOptions.method || "GET",
    headers: requestOptions.headers,
    hasAuth: !!authToken,
  });

  try {
    const response = await fetch(url, requestOptions);
    const duration = Date.now() - startTime;

    if (!response.ok) {
      const errorText = await response.text();
      let errorData;

      try {
        errorData = JSON.parse(errorText);
      } catch {
        errorData = { message: errorText };
      }

      const error = new Error(
        `HTTP ${response.status}: ${response.statusText}`
      );
      error.status = response.status;
      error.statusText = response.statusText;
      error.responseData = errorData;
      error.url = url;
      error.duration = duration;

      logger.error("API request failed", error, {
        url,
        status: response.status,
        statusText: response.statusText,
        responseBody: errorText,
        duration,
      });

      throw error;
    }

    const data = await response.json();

    // Safely calculate data size without causing circular reference issues
    let dataSize = 0;
    try {
      dataSize = JSON.stringify(data).length;
    } catch (error) {
      // If circular reference error, estimate size differently
      dataSize = data
        ? typeof data === "string"
          ? data?.length || 0
          : "unknown"
        : 0;
    }

    logger.info("API request successful", {
      url,
      status: response.status,
      duration,
      dataSize,
    });

    return data;
  } catch (error) {
    const duration = Date.now() - startTime;

    if (error.name === "TypeError" && error.message.includes("fetch")) {
      const networkError = new Error(
        "Network error: Unable to connect to server"
      );
      networkError.isNetworkError = true;
      networkError.originalError = error;
      networkError.url = url;
      networkError.duration = duration;

      logger.error("Network error", networkError, { url, duration });
      throw networkError;
    }

    // Re-throw API errors with additional context
    if (error.status) {
      error.duration = duration;
      throw error;
    }

    // Unknown error
    const unknownError = new Error("Unknown error occurred");
    unknownError.originalError = error;
    unknownError.url = url;
    unknownError.duration = duration;

    logger.error("Unknown error", unknownError, { url, duration });
    throw unknownError;
  }
};

// Common API patterns for different data types
export const apiPatterns = {
  // Standard data fetching pattern
  fetchData: (endpoint, componentName) => {
    return apiCall(endpoint, { method: "GET" }, componentName);
  },

  // Pattern for posting data
  postData: (endpoint, data, componentName) => {
    return apiCall(
      endpoint,
      {
        method: "POST",
        body: JSON.stringify(data),
      },
      componentName
    );
  },

  // Pattern for fetching paginated data
  fetchPaginatedData: (endpoint, page = 1, limit = 25, componentName) => {
    const params = new URLSearchParams({ page, limit });
    return apiCall(`${endpoint}?${params}`, { method: "GET" }, componentName);
  },

  // Pattern for fetching filtered data
  fetchFilteredData: (endpoint, filters = {}, componentName) => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        params.append(key, value);
      }
    });

    const url = params.toString() ? `${endpoint}?${params}` : endpoint;
    return apiCall(url, { method: "GET" }, componentName);
  },

  // Pattern for real-time data with caching
  fetchRealtimeData: async (endpoint, componentName, cacheKey) => {
    const cacheExpiry = 60000; // 1 minute
    const now = Date.now();

    // Check cache first
    const cached = sessionStorage.getItem(cacheKey);
    if (cached) {
      const { data, timestamp } = JSON.parse(cached);
      if (now - timestamp < cacheExpiry) {
        createLogger(componentName).debug("Using cached data", { cacheKey });
        return data;
      }
    }

    // Fetch fresh data
    const data = await apiCall(endpoint, { method: "GET" }, componentName);

    // Cache the result safely (avoid circular references)
    try {
      sessionStorage.setItem(
        cacheKey,
        JSON.stringify({
          data,
          timestamp: now,
        })
      );
    } catch (error) {
      // Skip caching if data contains circular references
      createLogger(componentName).warn(
        "Cannot cache data due to circular references",
        {
          cacheKey,
          error: error.message,
        }
      );
    }

    return data;
  },
};

// React Query configuration helper
export const createQueryConfig = (componentName) => ({
  defaultOptions: {
    queries: {
      staleTime: 60000, // 1 minute
      cacheTime: 300000, // 5 minutes
      refetchOnWindowFocus: false,
      retry: (failureCount, error) => {
        // Don't retry on auth errors
        if (error?.status === 401 || error?.status === 403) {
          return false;
        }
        // Retry up to 3 times for other errors
        return failureCount < 3;
      },
      onError: (error) => {
        createLogger(componentName).error("React Query error", error);
      },
    },
  },
});

// Standardized error handling for React components
export const withErrorHandling = (Component, componentName) => {
  return function ErrorHandledComponent(props) {
    const logger = createLogger(componentName);

    React.useEffect(() => {
      const handleError = (event) => {
        logger.error("Unhandled error in component", event.error, {
          componentName,
          props: Object.keys(props),
        });
      };

      window.addEventListener("error", handleError);
      return () => window.removeEventListener("error", handleError);
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    return <Component {...props} />;
  };
};

export default {
  apiCall,
  apiPatterns,
  createLogger,
  createQueryConfig,
  withErrorHandling,
};
