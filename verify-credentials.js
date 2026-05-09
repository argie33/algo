#!/usr/bin/env node
/**
 * Credential Verification Script
 * Validates that all credentials are properly configured
 *
 * Usage: node verify-credentials.js
 */

const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, '.env.local') });

// ANSI Colors
const colors = {
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  reset: '\x1b[0m',
  bold: '\x1b[1m',
};

function log(color, symbol, message) {
  console.log(`${color}${symbol}${colors.reset} ${message}`);
}

function checkEnv(varName) {
  const value = process.env[varName];
  if (!value) {
    return null;
  }

  // Mask sensitive values
  if (varName.includes('PASSWORD') || varName.includes('SECRET') || varName.includes('KEY')) {
    return '***masked***';
  }
  return value;
}

function validateJWTSecret() {
  const secret = process.env.JWT_SECRET;
  if (!secret) return { ok: false, msg: 'NOT SET' };
  if (secret.length < 32) {
    return { ok: false, msg: `TOO SHORT (${secret.length} chars, min 32)` };
  }
  return { ok: true, msg: `OK (${secret.length} chars)` };
}

function maskValue(key) {
  if (key.includes('PASSWORD') || key.includes('SECRET') || key.includes('KEY')) {
    return '***masked***';
  }
  return process.env[key];
}

console.log('\n' + colors.blue + '═══════════════════════════════════════════════════════' + colors.reset);
console.log(colors.blue + colors.bold + '    CREDENTIAL CONFIGURATION VERIFICATION' + colors.reset);
console.log(colors.blue + '═══════════════════════════════════════════════════════' + colors.reset + '\n');

let passed = 0;
let total = 0;
const results = {};

// Database Configuration
console.log(colors.blue + colors.bold + 'Database Configuration:' + colors.reset);
console.log('────────────────────────');

const dbVars = ['DB_HOST', 'DB_PORT', 'DB_USER', 'DB_PASSWORD', 'DB_NAME'];
let dbOk = true;

for (const v of dbVars) {
  const val = checkEnv(v);
  if (!val) {
    log(colors.red, '✗', `${v} not set`);
    dbOk = false;
  } else {
    log(colors.green, '✓', `${v} = ${val}`);
  }
}

const secretArn = process.env.DB_SECRET_ARN;
if (secretArn) {
  log(colors.green, '✓', `DB_SECRET_ARN is set (AWS Secrets Manager)`);
} else {
  log(colors.yellow, 'ℹ', 'DB_SECRET_ARN not set (using environment variables)');
}

results.database = dbOk ? 'CONFIGURED' : 'MISSING';
if (dbOk) passed++;
total++;
console.log('');

// Alpaca Configuration
console.log(colors.blue + colors.bold + 'Alpaca Configuration:' + colors.reset);
console.log('──────────────────────');

let alpacaOk = false;

const apiKeyId = process.env.APCA_API_KEY_ID || process.env.ALPACA_API_KEY;
if (apiKeyId) {
  if (process.env.APCA_API_KEY_ID) {
    log(colors.green, '✓', 'APCA_API_KEY_ID is set (official)');
  } else {
    log(colors.yellow, '⚠', 'Using legacy ALPACA_API_KEY (prefer APCA_API_KEY_ID)');
  }
  alpacaOk = true;
} else {
  log(colors.red, '✗', 'No API Key found (APCA_API_KEY_ID or ALPACA_API_KEY)');
}

const apiSecret = process.env.APCA_API_SECRET_KEY || process.env.ALPACA_API_SECRET || process.env.ALPACA_SECRET_KEY;
if (apiSecret) {
  if (process.env.APCA_API_SECRET_KEY) {
    log(colors.green, '✓', 'APCA_API_SECRET_KEY is set (official)');
  } else {
    log(colors.yellow, '⚠', 'Using legacy secret key variant');
  }
} else {
  log(colors.red, '✗', 'No API Secret found');
  alpacaOk = false;
}

const paperTradingVal = process.env.ALPACA_PAPER_TRADING;
if (paperTradingVal === 'true') {
  log(colors.green, '✓', 'ALPACA_PAPER_TRADING = true (safe for dev)');
} else if (paperTradingVal === 'false') {
  log(colors.yellow, '⚠', 'ALPACA_PAPER_TRADING = false (LIVE TRADING - be careful!)');
} else {
  log(colors.yellow, 'ℹ', 'ALPACA_PAPER_TRADING not set (default: true)');
}

results.alpaca = alpacaOk ? 'CONFIGURED' : 'MISSING';
if (alpacaOk) passed++;
total++;
console.log('');

// Authentication
console.log(colors.blue + colors.bold + 'Authentication:' + colors.reset);
console.log('────────────────');

const jwtValidation = validateJWTSecret();
if (jwtValidation.ok) {
  log(colors.green, '✓', `JWT_SECRET: ${jwtValidation.msg}`);
  results.auth = 'CONFIGURED';
  passed++;
} else {
  log(colors.red, '✗', `JWT_SECRET: ${jwtValidation.msg}`);
  results.auth = 'MISSING';
}
total++;

const cognitoPool = checkEnv('COGNITO_USER_POOL_ID');
if (cognitoPool) {
  log(colors.green, '✓', 'COGNITO_USER_POOL_ID is set');
} else {
  log(colors.yellow, 'ℹ', 'COGNITO_USER_POOL_ID not set (optional)');
}

const cognitoClient = checkEnv('COGNITO_CLIENT_ID');
if (cognitoClient) {
  log(colors.green, '✓', 'COGNITO_CLIENT_ID is set');
} else {
  log(colors.yellow, 'ℹ', 'COGNITO_CLIENT_ID not set (optional)');
}

console.log('');

// Email Configuration
console.log(colors.blue + colors.bold + 'Email & Alerting:' + colors.reset);
console.log('─────────────────');

const emailVars = ['ALERT_SMTP_HOST', 'ALERT_SMTP_PORT', 'ALERT_SMTP_USER'];
let emailOk = true;

for (const v of emailVars) {
  const val = checkEnv(v);
  if (!val) {
    log(colors.yellow, 'ℹ', `${v} not set (alerts disabled)`);
    emailOk = false;
  } else {
    log(colors.green, '✓', `${v} is set`);
  }
}

const smtpPassword = checkEnv('ALERT_SMTP_PASSWORD');
if (!smtpPassword) {
  log(colors.yellow, 'ℹ', 'ALERT_SMTP_PASSWORD not set (alerts disabled)');
}

const alertEmail = checkEnv('ALERT_EMAIL_TO');
if (!alertEmail) {
  log(colors.yellow, 'ℹ', 'ALERT_EMAIL_TO not set (alerts disabled)');
}

results.email = emailOk ? 'CONFIGURED' : 'NOT CONFIGURED';
if (emailOk) passed++;
total++;
console.log('');

// AWS Configuration
console.log(colors.blue + colors.bold + 'AWS Configuration:' + colors.reset);
console.log('──────────────────');

const awsRegion = process.env.AWS_REGION || 'us-east-1';
log(colors.green, '✓', `AWS_REGION = ${awsRegion}`);

results.aws = 'CONFIGURED';
passed++;
total++;
console.log('');

// Environment Settings
console.log(colors.blue + colors.bold + 'Environment Settings:' + colors.reset);
console.log('─────────────────────');

const nodeEnv = process.env.NODE_ENV || 'development';
const devBypass = process.env.ALLOW_DEV_BYPASS;
const localDev = process.env.LOCAL_DEV_MODE;

log(colors.green, '✓', `NODE_ENV = ${nodeEnv}`);

if (devBypass === 'true') {
  log(colors.yellow, '⚠', 'ALLOW_DEV_BYPASS = true (dev mode only)');
} else {
  log(colors.green, '✓', 'ALLOW_DEV_BYPASS = disabled (secure)');
}

if (localDev === 'true') {
  log(colors.green, '✓', 'LOCAL_DEV_MODE = true');
} else {
  log(colors.yellow, 'ℹ', 'LOCAL_DEV_MODE not set');
}

console.log('');

// Summary
console.log(colors.blue + '═══════════════════════════════════════════════════════' + colors.reset);
console.log(colors.blue + colors.bold + '    VERIFICATION SUMMARY' + colors.reset);
console.log(colors.blue + '═══════════════════════════════════════════════════════' + colors.reset);
console.log('');

console.log(`Database:     ${results.database}`);
console.log(`Alpaca:       ${results.alpaca}`);
console.log(`Auth:         ${results.auth}`);
console.log(`Email:        ${results.email}`);
console.log(`AWS:          ${results.aws}`);

console.log('');
console.log(`Passed: ${passed}/${total}`);
console.log('');

// Final Status
if (passed === total) {
  console.log(colors.green + colors.bold + '═════════════════════════════════════════════════════' + colors.reset);
  console.log(colors.green + colors.bold + '           ALL CHECKS PASSED ✓' + colors.reset);
  console.log(colors.green + colors.bold + '  System is ready for local development or deployment' + colors.reset);
  console.log(colors.green + colors.bold + '═════════════════════════════════════════════════════' + colors.reset);
  console.log('');
  process.exit(0);
} else {
  console.log(colors.red + colors.bold + '═════════════════════════════════════════════════════' + colors.reset);
  console.log(colors.red + colors.bold + '        SOME CHECKS FAILED ✗' + colors.reset);
  console.log(colors.red + colors.bold + '  Please fix missing credentials before continuing' + colors.reset);
  console.log(colors.red + colors.bold + '═════════════════════════════════════════════════════' + colors.reset);
  console.log('');
  process.exit(1);
}
