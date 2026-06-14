// Frontend Runtime Configuration Template
// This file shows the shape of config.js. Do NOT hardcode real values here.
//
// config.js is generated at runtime — never committed to git.
//   Local dev:  scripts/setup-local-dev.ps1 generates it from AWS Secrets Manager
//   Production: GitHub Actions generates it from Terraform outputs
//
// config.js is loaded by index.html before the React bundle, so window.__CONFIG__
// is available synchronously at app startup.

window.__CONFIG__ = {
  // API_URL:
  //   - Local dev (Vite proxy mode): "" — Vite proxies /api/* to VITE_PROXY_TARGET
  //   - Production: "https://<cloudfront-domain>" — set by CI from Terraform output
  "API_URL": "",

  // Cognito User Pool — values come from Terraform outputs / Secrets Manager.
  // Run scripts/setup-local-dev.ps1 to populate these for local dev.
  "USER_POOL_ID": "REPLACE_WITH_COGNITO_USER_POOL_ID",
  "USER_POOL_CLIENT_ID": "REPLACE_WITH_COGNITO_CLIENT_ID",
  "USER_POOL_DOMAIN": "REPLACE_WITH_COGNITO_DOMAIN",
  "AWS_REGION": "us-east-1",

  // ENVIRONMENT: Controls UI behavior and API error handling
  // - "development": Full error messages, Vite proxy, console logs enabled
  // - "production":  Sanitized errors, CloudFront domain, minimal logging
  "ENVIRONMENT": "development"
};
