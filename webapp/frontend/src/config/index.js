// API Configuration
// In development: use empty string to leverage Vite proxy to localhost:3001
// In production: use VITE_API_URL if set (e.g. CloudFront URL), or empty string
// for relative-path mode (works when frontend is served from the same CloudFront domain).
// Runtime config (window.__CONFIG__.API_URL from config.js) takes precedence over
// this build-time value — see services/api.js getApiConfig().
const API_BASE_URL = (() => {
  if (import.meta.env.DEV) {
    return '';
  }
  // Allow empty string: when VITE_API_URL is unset/empty, relative paths are used
  // and CloudFront routes /api/* to the API Gateway (same-origin, no CORS needed).
  return import.meta.env.VITE_API_URL || '';
})();

export { API_BASE_URL };

// Default configuration export
export { CONFIG, PRODUCTION_CONFIG, getEnvironmentConfig, validateConfig } from './production.js';

