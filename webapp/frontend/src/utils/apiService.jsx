// Standardized API Service with consistent error handling and logging
import React from "react";
import { getApiConfig } from "../services/api";
import { tokenManager } from "../services/tokenManager";

// Enhanced logging utility
export const createLogger = (componentName) => ({
  info: (message, data) => {
    // Reserved for detailed debugging - currently suppressed to reduce console noise
    // Enable this in production debugging only if needed
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
    let _safeData;
    try {
      _safeData =
        data && typeof data === "object"
          ? JSON.parse(JSON.stringify(data))
          : data;
    } catch (error) {
      _safeData = data
        ? String(data)
        : "Unable to stringify data (circular reference)";
    }
    if (import.meta.env && import.meta.env.DEV) {
      console.warn(`[${componentName}] ${message}`, _safeData);
    }
  },
  debug: (message, data) => {
    if (process.env.NODE_ENV === "development") {
      // Safe data handling for debug to avoid circular references
      let _safeData;
      try {
        _safeData =
          data && typeof data === "object"
            ? JSON.parse(JSON.stringify(data))
            : data;
      } catch (error) {
        _safeData = data
          ? String(data)
          : "Unable to stringify data (circular reference)";
      }
      console.debug(`[${componentName}] ${message}`, _safeData);
    }
  },
});

// Get stored auth token for API requests (strict Cognito only)
const getAuthToken = () => {
  try {
    // Use tokenManager for consistent token retrieval
    return tokenManager.getToken('access');
  } catch (error) {
    console.warn('[apiService] Failed to retrieve auth token:', error?.message || error);
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
      } catch (parseErr) {
        console.error('[API] Failed to parse error response JSON:', parseErr?.message || parseErr);
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

    // Validate content-type before parsing JSON (allow charset and other JSON variations)
    const contentType = response.headers.get('content-type') || '';
    const isJsonContentType = contentType.startsWith('application/json');
    if (contentType && !isJsonContentType) {
      // Log warning for non-JSON responses but still try to parse (some APIs omit content-type)
      logger.warn('API response has non-JSON content-type, attempting to parse anyway', {
        contentType,
        url,
        status: response.status,
      });
    }

    let data;
    try {
      data = await response.json();
    } catch (parseError) {
      logger.error('Failed to parse JSON response', parseError, {
        url,
        status: response.status,
        contentType,
      });
      throw new Error(
        `Failed to parse server response as JSON: ${parseError.message}`
      );
    }

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

    // Check for data freshness warnings
    if (data && data.data_freshness) {
      const freshness = data.data_freshness;
      if (freshness.is_stale) {
        console.warn(
          `⚠️ Stale data from ${url}: ${freshness.warning || 'Data is older than expected'}`,
          freshness
        );
      }
    }

    // Check for NULL values in expected fields
    if (data && data.items && data.items.length > 0) {
      const item = data.items[0];
      const requiredFieldsByEndpoint = {
        '/api/scores': ['symbol', 'momentum_score', 'composite_score'],
        '/api/signals': ['symbol', 'ema_21', 'adx', 'signal'],
        '/api/market': ['vix_level']
      };

      const endpoint = url.split('?')[0]; // Remove query params
      const requiredFields = requiredFieldsByEndpoint[endpoint] || [];

      for (const field of requiredFields) {
        if (item[field] == null) {
          console.error(
            `❌ Expected field "${field}" is NULL/undefined in ${url}`,
            { item, endpoint }
          );
        }
      }
    }

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
      
    }, []);

    return <Component {...props} />;
  };
};

export { getApiConfig };

export default {
  apiCall,
  apiPatterns,
  createLogger,
  createQueryConfig,
  withErrorHandling,
  getApiConfig,
};

