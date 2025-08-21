// Standardized API Service with consistent error handling and logging
import React from "react";
import { getApiConfig } from "../services/api";

// Enhanced logging utility
export const createLogger = (componentName) => ({
  info: (message, data) => {
    console.log(`[${componentName}] ${message}`, data);
  },
  error: (message, error, context) => {
    console.error(`[${componentName}] ${message}`, {
      error: error?.message || error,
      stack: error?.stack,
      context,
      timestamp: new Date().toISOString(),
      component: componentName,
    });
  },
  warn: (message, data) => {
    console.warn(`[${componentName}] ${message}`, data);
  },
  debug: (message, data) => {
    if (process.env.NODE_ENV === "development") {
      console.debug(`[${componentName}] ${message}`, data);
    }
  },
});

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

  const requestOptions = {
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
    ...options,
  };

  logger.info("Making API request", {
    url,
    method: requestOptions.method || "GET",
    headers: requestOptions.headers,
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

    logger.info("API request successful", {
      url,
      status: response.status,
      duration,
      dataSize: JSON.stringify(data).length,
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

    // Cache the result
    sessionStorage.setItem(
      cacheKey,
      JSON.stringify({
        data,
        timestamp: now,
      })
    );

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
