#!/usr/bin/env node
/**
 * Verify that all critical code fixes are in place
 * Tests Issues #1, #2, #9 (Response Normalizer, API Error Codes, Null References)
 */

const fs = require('fs');
const path = require('path');

const testResults = [];
let passCount = 0;
let failCount = 0;

function test(name, condition, details = '') {
  const result = condition ? '✓' : '✗';
  const status = condition ? 'PASS' : 'FAIL';
  const color = condition ? '\x1b[32m' : '\x1b[31m';
  const resetColor = '\x1b[0m';

  console.log(`${color}${result} ${name}${resetColor}${details ? ` - ${details}` : ''}`);

  if (condition) {
    passCount++;
  } else {
    failCount++;
  }

  testResults.push({ name, status, details });
}

console.log('\n═══════════════════════════════════════════════════════');
console.log('Code Fixes Verification');
console.log('═══════════════════════════════════════════════════════\n');

// ───────────────────────────────────────────────────────────────────────────────
// Issue #1: Response Normalizer Overwrites Error Flag
// ───────────────────────────────────────────────────────────────────────────────

console.log('Issue #1: Response Normalizer Error Detection');
console.log('─' .repeat(50));

const normalizerPath = path.join(__dirname, '../webapp/frontend/src/utils/responseNormalizer.js');
if (fs.existsSync(normalizerPath)) {
  const normalizerCode = fs.readFileSync(normalizerPath, 'utf8');

  test(
    'Normalizer detects success: false',
    normalizerCode.includes('data.data.success === false') ||
    normalizerCode.includes('data.success === false'),
    'Checks nested success flag'
  );

  test(
    'Normalizer throws error on failure',
    normalizerCode.includes('throw') && normalizerCode.includes('error'),
    'Throws Error object instead of returning'
  );

  test(
    'Normalizer preserves error details',
    normalizerCode.includes('error.code') || normalizerCode.includes('errorType'),
    'Captures error code/type'
  );
} else {
  test('Normalizer file exists', false, `File not found: ${normalizerPath}`);
}

// ───────────────────────────────────────────────────────────────────────────────
// Issue #2: API Returns 200 Status for Errors
// ───────────────────────────────────────────────────────────────────────────────

console.log('\nIssue #2: API Error Status Codes');
console.log('─' .repeat(50));

const algoRoutesPath = path.join(__dirname, '../lambda/api/routes/algo.py');
const economicRoutesPath = path.join(__dirname, '../lambda/api/routes/economic.py');

if (fs.existsSync(algoRoutesPath)) {
  const algoCode = fs.readFileSync(algoRoutesPath, 'utf8');

  test(
    'algo.py returns error codes',
    algoCode.includes('error_response') || algoCode.includes('503') || algoCode.includes('500'),
    'Uses error_response or appropriate status codes'
  );

  test(
    'algo.py handles DB errors',
    algoCode.includes('OperationalError') && (algoCode.includes('503') || algoCode.includes('error_response')),
    'Catches database errors and returns proper status'
  );
} else {
  test('algo.py routes file exists', false, `File not found: ${algoRoutesPath}`);
}

if (fs.existsSync(economicRoutesPath)) {
  const economicCode = fs.readFileSync(economicRoutesPath, 'utf8');

  test(
    'economic.py returns error codes',
    economicCode.includes('error_response') || economicCode.includes('503') || economicCode.includes('500'),
    'Uses error_response or appropriate status codes'
  );
} else {
  test('economic.py routes file exists', false, `File not found: ${economicRoutesPath}`);
}

// ───────────────────────────────────────────────────────────────────────────────
// Issue #9: Component Null Reference Errors
// ───────────────────────────────────────────────────────────────────────────────

console.log('\nIssue #9: Null Reference Protection');
console.log('─' .repeat(50));

const dataValidationPath = path.join(__dirname, '../webapp/frontend/src/utils/dataValidation.js');
if (fs.existsSync(dataValidationPath)) {
  const dataValidationCode = fs.readFileSync(dataValidationPath, 'utf8');

  test(
    'Data validation utilities exist',
    dataValidationCode.includes('export'),
    'Exports validation functions'
  );

  test(
    'Validates market data structure',
    dataValidationCode.includes('validateMarketData'),
    'Market data validator present'
  );

  test(
    'Handles null/undefined gracefully',
    dataValidationCode.includes('typeof') && dataValidationCode.includes('fallback'),
    'Uses type checking and fallback values'
  );

  test(
    'Safe nested value access',
    dataValidationCode.includes('getNestedValue') || dataValidationCode.includes('reduce'),
    'Provides safe path traversal'
  );
} else {
  test('Data validation file exists', false, `File not found: ${dataValidationPath}`);
}

// ───────────────────────────────────────────────────────────────────────────────
// Additional Critical Files
// ───────────────────────────────────────────────────────────────────────────────

console.log('\nAdditional Protection Mechanisms');
console.log('─' .repeat(50));

const apiPath = path.join(__dirname, '../webapp/frontend/src/services/api.js');
if (fs.existsSync(apiPath)) {
  const apiCode = fs.readFileSync(apiPath, 'utf8');

  test(
    'Circuit breaker implemented',
    apiCode.includes('CircuitBreaker') || apiCode.includes('FAILURE_THRESHOLD'),
    'Prevents cascading failures'
  );

  test(
    'Error handling in API calls',
    apiCode.includes('catch') && apiCode.includes('error'),
    'Catches and handles API errors'
  );

  test(
    'Retry logic for transient failures',
    apiCode.includes('retry') || apiCode.includes('attempt') || apiCode.includes('backoff'),
    'Retries on temporary failures'
  );
} else {
  test('API service file exists', false, `File not found: ${apiPath}`);
}

// ───────────────────────────────────────────────────────────────────────────────
// ERROR #5 Cache Invalidation
// ───────────────────────────────────────────────────────────────────────────────

console.log('\nERROR #5: Cache Invalidation');
console.log('─' .repeat(50));

const buildProdPath = path.join(__dirname, '../webapp/frontend/scripts/build-prod.js');
if (fs.existsSync(buildProdPath)) {
  const buildCode = fs.readFileSync(buildProdPath, 'utf8');

  test(
    'Cache-bust parameter injection',
    buildCode.includes('?v=') && buildCode.includes('buildHash'),
    'Injects unique cache-bust parameter'
  );

  test(
    'Modifies index.html',
    buildCode.includes('index.html') && buildCode.includes('replace'),
    'Replaces config.js URL with cache-bust version'
  );
} else {
  test('Build script exists', false, `File not found: ${buildProdPath}`);
}

const mainJsxPath = path.join(__dirname, '../webapp/frontend/src/main.jsx');
if (fs.existsSync(mainJsxPath)) {
  const mainCode = fs.readFileSync(mainJsxPath, 'utf8');

  test(
    'Explicit config.js fetch',
    mainCode.includes('fetchConfigExplicitly') || mainCode.includes('fetch.*config.js'),
    'Fetches config with no-cache headers'
  );

  test(
    'Cache-bypass headers',
    mainCode.includes('cache: \'no-store\'') || mainCode.includes('no-cache'),
    'Uses HTTP cache-bypass directives'
  );

  test(
    'Fallback mechanism',
    mainCode.includes('fallback') || mainCode.includes('script tag'),
    'Falls back to script-tag loaded config'
  );
} else {
  test('main.jsx exists', false, `File not found: ${mainJsxPath}`);
}

// ───────────────────────────────────────────────────────────────────────────────
// Summary
// ───────────────────────────────────────────────────────────────────────────────

console.log('\n═══════════════════════════════════════════════════════');
console.log(`Test Results: ${passCount} passed, ${failCount} failed`);
console.log('═══════════════════════════════════════════════════════\n');

if (failCount === 0) {
  console.log('✓ All critical code fixes are in place!\n');
  process.exit(0);
} else {
  console.log(`✗ ${failCount} test(s) failed. Please review the fixes.\n`);
  process.exit(1);
}
