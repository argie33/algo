// Frontend Runtime Configuration Template
// This file is a template showing all available configuration options.
//
// During development: Copy to config.js with LOCAL values (empty API_URL for Vite proxy)
// During deployment: GitHub Actions generates config.js with PRODUCTION values
//
// NEVER commit config.js to git. Each environment must generate it at build time.

window.__CONFIG__ = {
  // API_URL: Set by environment
  // - Local dev: "" (empty = use Vite proxy to localhost:3001)
  // - Staging: "" or staging API URL
  // - Production: "https://d2u93283nn45h2.cloudfront.net" (CloudFront domain)
  "API_URL": "",

  // Cognito User Pool Configuration
  // All environments point to the same Cognito pool (us-east-1_XJpLb9SKX)
  // The ENVIRONMENT flag controls behavior, not the Cognito endpoint
  "USER_POOL_ID": "us-east-1_XJpLb9SKX",
  "USER_POOL_CLIENT_ID": "6smb0vrcidd9kvhju2kn2a3qrl",
  "USER_POOL_DOMAIN": "https://algo-dev.auth.us-east-1.amazoncognito.com",
  "AWS_REGION": "us-east-1",

  // ENVIRONMENT: Controls UI behavior and API error handling
  // - "development": Shows full error messages, uses Vite proxy, console logs enabled
  // - "production": Sanitized errors, uses CloudFront domain, minimal logging
  "ENVIRONMENT": "development"
};
