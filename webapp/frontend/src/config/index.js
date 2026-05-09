// API Configuration
// In development: use empty string to leverage Vite proxy to localhost:3001
// In production: use VITE_API_URL from build-time environment
export const API_BASE_URL = import.meta.env.VITE_API_URL || (import.meta.env.DEV ? '' : 'http://localhost:3001');

// Default configuration export
export { CONFIG, PRODUCTION_CONFIG, getEnvironmentConfig, validateConfig } from './production.js';
