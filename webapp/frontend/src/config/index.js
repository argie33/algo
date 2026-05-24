// API Configuration
// In development: use empty string to leverage Vite proxy to localhost:3001
// In production: MUST use VITE_API_URL (required) - NO localhost fallback
const API_BASE_URL = (() => {
  if (import.meta.env.DEV) {
    // Development: use empty string (Vite proxy handles routing to API)
    return '';
  }
  // Production: require explicit VITE_API_URL environment variable
  const prodUrl = import.meta.env.VITE_API_URL;
  if (!prodUrl) {
    throw new Error(
      'Production Error: VITE_API_URL environment variable is required. ' +
      'Set it during build: VITE_API_URL=https://api.example.com npm run build'
    );
  }
  return prodUrl;
})();

export { API_BASE_URL };

// Default configuration export
export { CONFIG, PRODUCTION_CONFIG, getEnvironmentConfig, validateConfig } from './production.js';

