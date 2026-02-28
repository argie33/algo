// API Configuration
export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:3000';

// Default configuration export
export { CONFIG, PRODUCTION_CONFIG, getEnvironmentConfig, validateConfig } from './production.js';
