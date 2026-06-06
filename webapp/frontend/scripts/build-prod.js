#!/usr/bin/env node
/**
 * Production build wrapper that ensures all environment variables are passed
 * to setup-prod.js and Vite with proper error handling (cross-platform).
 *
 * Usage: node scripts/build-prod.js [API_URL] [environment]
 */

import { execSync } from "child_process";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.join(__dirname, "..");

// Extract environment variables with command-line arg fallbacks
const apiUrl = process.argv[2] || process.env.VITE_API_URL || "";
const environment = process.argv[3] || process.env.VITE_ENVIRONMENT || "production";
const userPoolId = process.argv[4] || process.env.VITE_COGNITO_USER_POOL_ID || "";
const clientId = process.argv[5] || process.env.VITE_COGNITO_CLIENT_ID || "";
const cognitoDomain = process.argv[6] || process.env.VITE_COGNITO_DOMAIN || "";
const cloudfrontUrl = process.argv[7] || process.env.VITE_CLOUDFRONT_DOMAIN || "";

// Validate critical variables before build
if (!apiUrl) {
  console.warn("⚠️  WARNING: API_URL is empty - frontend may not reach API");
}

if (!userPoolId && !clientId) {
  console.warn("⚠️  WARNING: Cognito credentials not set - authentication will be disabled");
}

console.log("🔨 Starting production build...");
console.log(`📝 API_URL: ${apiUrl || "(empty)"}`);
console.log(`📝 Environment: ${environment}`);
console.log(`📝 Cognito User Pool ID: ${userPoolId ? "SET" : "(not set)"}`);

try {
  // Run setup-prod.js EXPLICITLY with all arguments
  console.log("\n📝 Running setup-prod.js...");
  execSync(`node setup-prod.js "${apiUrl}" "${environment}" "${userPoolId}" "${clientId}" "${cognitoDomain}" "${cloudfrontUrl}"`, {
    cwd: __dirname,
    stdio: "inherit",
  });

  // Verify config.js was created
  const publicConfigPath = path.join(projectRoot, "public", "config.js");
  if (!fs.existsSync(publicConfigPath)) {
    console.error("❌ ERROR: config.js not created in public/");
    process.exit(1);
  }

  const configContent = fs.readFileSync(publicConfigPath, "utf8");
  console.log("✓ config.js created successfully");
  console.log(configContent.substring(0, 200) + "...\n");

  // Run Vite build with all environment variables explicitly set
  console.log("📦 Running Vite build...");
  const env = {
    ...process.env,
    VITE_API_URL: apiUrl,
    VITE_ENVIRONMENT: environment,
    VITE_COGNITO_USER_POOL_ID: userPoolId,
    VITE_COGNITO_CLIENT_ID: clientId,
    VITE_COGNITO_DOMAIN: cognitoDomain,
  };

  execSync("vite build", {
    cwd: projectRoot,
    stdio: "inherit",
    env,
  });

  // Verify dist/config.js exists
  const distConfigPath = path.join(projectRoot, "dist", "config.js");
  if (!fs.existsSync(distConfigPath)) {
    console.error("❌ ERROR: config.js not found in dist/ after Vite build");
    process.exit(1);
  }

  const distConfigContent = fs.readFileSync(distConfigPath, "utf8");

  // Validate config contains required values
  if (distConfigContent.includes('"API_URL": ""') && environment === "production") {
    console.warn("⚠️  WARNING: API_URL is empty in production build - frontend may not reach API");
  }

  if (distConfigContent.includes('"USER_POOL_ID": ""') && environment === "production") {
    console.warn("⚠️  WARNING: USER_POOL_ID is empty in production build - authentication disabled");
  }

  console.log("✓ Build completed successfully");
  console.log(`✓ dist/config.js generated: ${distConfigContent.substring(0, 100)}...`);
  process.exit(0);

} catch (error) {
  console.error("❌ Build failed:", error.message);
  process.exit(1);
}
