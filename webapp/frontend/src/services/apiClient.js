/**
 * CLEAN API CLIENT - Single source of truth for API communication
 *
 * Every response from the backend follows ONE format:
 * {
 *   success: boolean,
 *   data?: any,           // For single object responses
 *   items?: array,        // For list responses
 *   pagination?: object,  // For paginated responses
 *   error?: string,       // Only present on errors
 *   timestamp: string     // ISO timestamp
 * }
 *
 * This client normalizes all responses into a consistent format.
 */

import axios from 'axios';

// Create axios instance with base config
const axiosInstance = axios.create({
  baseURL: getBaseURL(),
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json'
  }
});

function getBaseURL() {
  // In development, use relative path
  if (import.meta?.env?.DEV) {
    return '/';
  }

  // In production, use API Gateway
  if (typeof window !== 'undefined' && window.__CONFIG__?.API_URL) {
    return window.__CONFIG__.API_URL;
  }

  if (typeof window !== 'undefined' && window.location.hostname === 'localhost') {
    return 'http://localhost:3001';
  }

  // AWS production
  return 'https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev';
}

// Response interceptor - normalize all responses
axiosInstance.interceptors.response.use(
  (response) => {
    const data = response.data;

    // Return normalized response
    return {
      success: data.success ?? true,
      data: data.data ?? null,
      items: data.items ?? null,
      pagination: data.pagination ?? null,
      error: data.error ?? null,
      timestamp: data.timestamp ?? new Date().toISOString(),
      // Raw response for debugging
      _raw: response
    };
  },
  (error) => {
    console.error('API Error:', error);

    // Normalize error response
    const errorData = error.response?.data || {};
    return Promise.reject({
      success: false,
      error: errorData.error || error.message || 'Request failed',
      timestamp: new Date().toISOString(),
      status: error.response?.status,
      _raw: error
    });
  }
);

/**
 * API Client with clean methods
 */
export const apiClient = {
  /**
   * GET request
   * @param {string} endpoint - API endpoint path
   * @param {object} params - Query parameters
   * @returns {Promise<NormalizedResponse>}
   */
  async get(endpoint, params = {}) {
    const response = await axiosInstance.get(endpoint, { params });
    return response;
  },

  /**
   * POST request
   * @param {string} endpoint - API endpoint path
   * @param {object} data - Request body
   * @returns {Promise<NormalizedResponse>}
   */
  async post(endpoint, data = {}) {
    const response = await axiosInstance.post(endpoint, data);
    return response;
  },

  /**
   * PUT request
   * @param {string} endpoint - API endpoint path
   * @param {object} data - Request body
   * @returns {Promise<NormalizedResponse>}
   */
  async put(endpoint, data = {}) {
    const response = await axiosInstance.put(endpoint, data);
    return response;
  },

  /**
   * DELETE request
   * @param {string} endpoint - API endpoint path
   * @returns {Promise<NormalizedResponse>}
   */
  async delete(endpoint) {
    const response = await axiosInstance.delete(endpoint);
    return response;
  },

  /**
   * PATCH request
   * @param {string} endpoint - API endpoint path
   * @param {object} data - Request body
   * @returns {Promise<NormalizedResponse>}
   */
  async patch(endpoint, data = {}) {
    const response = await axiosInstance.patch(endpoint, data);
    return response;
  }
};

export default apiClient;
