#!/usr/bin/env node
/**
 * Test script to validate config.js cache behavior
 * Verifies that all cache-busting mechanisms are in place
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
console.log('Config.js Cache Behavior Validation');
console.log('═══════════════════════════════════════════════════════\n');

// ───────────────────────────────────────────────────────────────────────────────
// Test 1: Build Process Cache Busting
// ───────────────────────────────────────────────────────────────────────────────

console.log('Test 1: Build Process Cache Busting');
console.log('─' .repeat(50));

const buildProdPath = path.join(__dirname, '../webapp/frontend/scripts/build-prod.js');
if (fs.existsSync(buildProdPath)) {
  const buildCode = fs.readFileSync(buildProdPath, 'utf8');

  test(
    'Cache-bust parameter uses unique hash',
    buildCode.includes('buildHash') && buildCode.includes('Date.now()'),
    'Uses Date.now() for unique ID'
  );

  test(
    'Replaces src attribute with cache-bust version',
    buildCode.includes('replace') && buildCode.includes('/config.js'),
    'Modifies index.html script tag'
  );

  test(
    'Validates config.js exists after build',
    buildCode.includes('dist/config.js') && buildCode.includes('existsSync'),
    'Checks dist/config.js exists'
  );

  // Extract the replacement pattern
  const replaceMatch = buildCode.match(/<script src="\/config\.js"/);
  test(
    'Source index.html has correct script tag format',
    replaceMatch !== null,
    'Pattern: <script src="/config.js"'
  );
} else {
  test('build-prod.js exists', false, `File not found: ${buildProdPath}`);
}

// ───────────────────────────────────────────────────────────────────────────────
// Test 2: Runtime Explicit Fetch
// ───────────────────────────────────────────────────────────────────────────────

console.log('\nTest 2: Runtime Explicit Fetch Mechanism');
console.log('─' .repeat(50));

const mainJsxPath = path.join(__dirname, '../webapp/frontend/src/main.jsx');
if (fs.existsSync(mainJsxPath)) {
  const mainCode = fs.readFileSync(mainJsxPath, 'utf8');

  test(
    'Explicit fetch function defined',
    mainCode.includes('fetchConfigExplicitly'),
    'Function name: fetchConfigExplicitly'
  );

  test(
    'Fetch includes cache-bust parameter',
    mainCode.includes('Date.now()') && mainCode.includes('bypass'),
    'Uses timestamp and random bypass parameter'
  );

  test(
    'Fetch uses no-cache directive',
    mainCode.includes("cache: 'no-store'"),
    'Cache mode: no-store'
  );

  test(
    'Fetch includes Pragma header',
    mainCode.includes("'Pragma'") && mainCode.includes('no-cache'),
    'Pragma: no-cache header'
  );

  test(
    'Fetch includes Cache-Control header',
    mainCode.includes("'Cache-Control'") && mainCode.includes('must-revalidate'),
    'Cache-Control: no-cache, no-store, must-revalidate'
  );

  test(
    'Handles fetch failure gracefully',
    mainCode.includes('catch') && mainCode.includes('fallback'),
    'Falls back to script tag if fetch fails'
  );

  test(
    'Config loaded before app render',
    mainCode.includes('configPromise') && mainCode.includes('root.render'),
    'Waits for config before rendering'
  );
} else {
  test('main.jsx exists', false, `File not found: ${mainJsxPath}`);
}

// ───────────────────────────────────────────────────────────────────────────────
// Test 3: S3 Upload Cache Headers
// ───────────────────────────────────────────────────────────────────────────────

console.log('\nTest 3: S3 Upload Cache Headers');
console.log('─' .repeat(50));

const workflowPath = path.join(__dirname, '../.github/workflows/deploy-all-infrastructure.yml');
if (fs.existsSync(workflowPath)) {
  const workflowCode = fs.readFileSync(workflowPath, 'utf8');

  test(
    'config.js uploaded separately',
    workflowCode.includes('--include "config.js"') && workflowCode.includes('--exclude "config.js"'),
    'Separate sync commands for config.js and others'
  );

  test(
    'config.js has no-cache headers',
    workflowCode.includes('no-cache, no-store, must-revalidate') && workflowCode.includes('config.js'),
    'Cache-Control: no-cache, no-store, must-revalidate'
  );

  test(
    'CloudFront invalidation runs',
    workflowCode.includes('cloudfront create-invalidation') && workflowCode.includes('--paths'),
    'Invalidates CloudFront cache with /* paths'
  );

  // Check if sed command is present (redundant but doesn't hurt)
  test(
    'GitHub Actions adds cache-bust to index.html',
    workflowCode.includes('sed') && workflowCode.includes('config.js?v='),
    'Uses sed to add ?v=timestamp parameter'
  );
} else {
  test('Workflow file exists', false, `File not found: ${workflowPath}`);
}

// ───────────────────────────────────────────────────────────────────────────────
// Test 4: CloudFront Configuration
// ───────────────────────────────────────────────────────────────────────────────

console.log('\nTest 4: CloudFront Cache Behavior');
console.log('─' .repeat(50));

const terraformPath = path.join(__dirname, '../terraform/modules/services/main.tf');
if (fs.existsSync(terraformPath)) {
  const terraformCode = fs.readFileSync(terraformPath, 'utf8');

  test(
    'config.js has dedicated cache behavior',
    terraformCode.includes('path_pattern') && terraformCode.includes('/config.js'),
    'Path pattern: /config.js*'
  );

  test(
    'config.js uses disabled caching policy',
    terraformCode.includes('managed_caching_disabled') && terraformCode.includes('config.js'),
    'Policy: Managed-CachingDisabled (no cache)'
  );

  test(
    'ISSUE #17 documented',
    terraformCode.includes('ISSUE #17') || terraformCode.includes('ISSUE.*17'),
    'Config cache fix is documented'
  );

  // Look for the actual config.js behavior block
  const configBehaviorMatch = terraformCode.match(/path_pattern\s*=\s*"\/config\.js.*?\n[\s\S]*?cache_policy_id[\s\S]*?managed_caching_disabled/m);
  test(
    'config.js behavior properly configured',
    configBehaviorMatch !== null,
    'Cache behavior found for /config.js*'
  );
} else {
  test('Terraform file exists', false, `File not found: ${terraformPath}`);
}

// ───────────────────────────────────────────────────────────────────────────────
// Test 5: HTML Template
// ───────────────────────────────────────────────────────────────────────────────

console.log('\nTest 5: HTML Template Configuration');
console.log('─' .repeat(50));

const htmlPath = path.join(__dirname, '../webapp/frontend/index.html');
if (fs.existsSync(htmlPath)) {
  const htmlCode = fs.readFileSync(htmlPath, 'utf8');

  test(
    'config.js loaded before main app',
    htmlCode.indexOf('<script src="/config.js') < htmlCode.indexOf('main.jsx'),
    'Script order: config.js before main.jsx'
  );

  test(
    'config.js has onerror handler',
    htmlCode.includes('onerror') && htmlCode.includes('__CONFIG_ERROR__'),
    'Catches config.js load failures'
  );

  test(
    'Error message is informative',
    htmlCode.includes('404') || htmlCode.includes('syntax error') || htmlCode.includes('server error'),
    'Provides debugging hints'
  );
} else {
  test('index.html exists', false, `File not found: ${htmlPath}`);
}

// ───────────────────────────────────────────────────────────────────────────────
// Test 6: Config Generation
// ───────────────────────────────────────────────────────────────────────────────

console.log('\nTest 6: Config Generation');
console.log('─' .repeat(50));

const setupProdPath = path.join(__dirname, '../webapp/frontend/scripts/setup-prod.js');
if (fs.existsSync(setupProdPath)) {
  const setupCode = fs.readFileSync(setupProdPath, 'utf8');

  test(
    'BUILD_TIME included in config',
    setupCode.includes('BUILD_TIME') && setupCode.includes('toISOString()'),
    'Includes timestamp for cache busting'
  );

  test(
    'API_URL injected into config',
    setupCode.includes('API_URL'),
    'Allows dynamic API URL configuration'
  );

  test(
    'Config written to public directory',
    setupCode.includes('public') && setupCode.includes('config.js'),
    'Output: webapp/frontend/public/config.js'
  );
} else {
  test('setup-prod.js exists', false, `File not found: ${setupProdPath}`);
}

// ───────────────────────────────────────────────────────────────────────────────
// Summary
// ───────────────────────────────────────────────────────────────────────────────

console.log('\n═══════════════════════════════════════════════════════');
console.log(`Test Results: ${passCount} passed, ${failCount} failed`);
console.log('═══════════════════════════════════════════════════════\n');

if (failCount === 0) {
  console.log('✓ All config.js cache mechanisms are in place!\n');
  process.exit(0);
} else {
  console.log(`✗ ${failCount} test(s) failed. Review the issues above.\n`);
  process.exit(1);
}
