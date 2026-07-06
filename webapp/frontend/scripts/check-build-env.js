#!/usr/bin/env node

/**
 * Ensure VITE_API_URL is set before building for production
 * Development builds use empty string (Vite proxy handles it)
 * Production builds REQUIRE explicit API URL
 */

const apiUrl = process.env.VITE_API_URL;
const environment = process.env.VITE_ENVIRONMENT || 'production';

// Only enforce API_URL for explicit production builds
if (environment === 'production' && !apiUrl) {
  console.error('\n❌ ERROR: VITE_API_URL environment variable is required for production builds\n');
  console.error('Set it before building:');
  console.error('  export VITE_API_URL=https://your-api-gateway-endpoint.com');
  console.error('  npm run build\n');
  console.error('Or use the convenience script:');
  console.error('  npm run build-prod\n');
  process.exit(1);
}

if (apiUrl) {
  console.log(`✓ Building with API URL: ${apiUrl}`);
} else {
  console.log(`ℹ  Building without explicit API URL (using relative paths for development)`);
}
