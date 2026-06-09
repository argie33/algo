#!/usr/bin/env node
/**
 * Diagnostic script to verify config.js is not stale
 * Checks: config.js BUILD_TIME, deployment timestamps, cache headers
 * Run after deployment to verify config.js freshness
 */

const fs = require('fs');
const path = require('path');

console.log('\n═══════════════════════════════════════════════════════');
console.log('Config.js Freshness Diagnostic');
console.log('═══════════════════════════════════════════════════════\n');

// ───────────────────────────────────────────────────────────────────────────────
// Check 1: Verify config.js exists and has BUILD_TIME
// ───────────────────────────────────────────────────────────────────────────────

console.log('Check 1: Config File Status');
console.log('─' .repeat(50));

const publicConfigPath = path.join(__dirname, '../webapp/frontend/public/config.js');
const distConfigPath = path.join(__dirname, '../webapp/frontend/dist/config.js');

let publicConfig = null;
let distConfig = null;
let publicBuildTime = null;
let distBuildTime = null;

if (fs.existsSync(publicConfigPath)) {
  const content = fs.readFileSync(publicConfigPath, 'utf8');
  const match = content.match(/"BUILD_TIME":\s*"([^"]+)"/);
  if (match) {
    publicBuildTime = match[1];
    console.log(`✓ public/config.js BUILD_TIME: ${publicBuildTime}`);
  } else {
    console.log('✗ public/config.js exists but no BUILD_TIME found');
  }
} else {
  console.log('⚠ public/config.js not found (expected for production builds)');
}

if (fs.existsSync(distConfigPath)) {
  const content = fs.readFileSync(distConfigPath, 'utf8');
  const match = content.match(/"BUILD_TIME":\s*"([^"]+)"/);
  if (match) {
    distBuildTime = match[1];
    console.log(`✓ dist/config.js BUILD_TIME: ${distBuildTime}`);
  } else {
    console.log('✗ dist/config.js exists but no BUILD_TIME found');
  }
} else {
  console.log('⚠ dist/config.js not found (build not run yet)');
}

// ───────────────────────────────────────────────────────────────────────────────
// Check 2: Compare timestamps (should match if recent build)
// ───────────────────────────────────────────────────────────────────────────────

console.log('\nCheck 2: Build Timestamp Consistency');
console.log('─' .repeat(50));

if (publicBuildTime && distBuildTime) {
  if (publicBuildTime === distBuildTime) {
    console.log('✓ public/ and dist/ config.js have same BUILD_TIME (synchronized)');
  } else {
    const publicTime = new Date(publicBuildTime);
    const distTime = new Date(distBuildTime);
    const diffMinutes = Math.abs(publicTime - distTime) / (1000 * 60);

    console.log(`⚠ Timestamps differ (${diffMinutes.toFixed(1)} minutes):`);
    console.log(`  public/: ${publicBuildTime}`);
    console.log(`  dist/:   ${distBuildTime}`);

    if (diffMinutes > 60) {
      console.log('  ⚠ More than 1 hour apart - dist/ is likely stale!');
      console.log('    Run: npm run build:prod');
    } else {
      console.log('  ℹ Normal in development (public/ updated separately from dist/)');
      console.log('    In production CI/CD, both are built together and will match');
    }
  }
}

// ───────────────────────────────────────────────────────────────────────────────
// Check 3: Verify cache headers in deployment config
// ───────────────────────────────────────────────────────────────────────────────

console.log('\nCheck 3: S3 Cache Header Configuration');
console.log('─' .repeat(50));

const workflowPath = path.join(__dirname, '../.github/workflows/deploy-all-infrastructure.yml');
if (fs.existsSync(workflowPath)) {
  const workflow = fs.readFileSync(workflowPath, 'utf8');

  if (workflow.includes('no-cache, no-store, must-revalidate') && workflow.includes('config.js')) {
    console.log('✓ S3 sync configured with no-cache headers for config.js');
  } else {
    console.log('✗ S3 sync NOT configured with no-cache headers');
  }
} else {
  console.log('⚠ Workflow file not found');
}

// ───────────────────────────────────────────────────────────────────────────────
// Check 4: Verify CloudFront cache behavior
// ───────────────────────────────────────────────────────────────────────────────

console.log('\nCheck 4: CloudFront Cache Behavior');
console.log('─' .repeat(50));

const terraformPath = path.join(__dirname, '../terraform/modules/services/main.tf');
if (fs.existsSync(terraformPath)) {
  const terraform = fs.readFileSync(terraformPath, 'utf8');

  // Check for /config.js* path pattern
  const pathPatternMatch = terraform.match(/path_pattern\s*=\s*"\/config\.js\*"/);
  if (pathPatternMatch) {
    console.log('✓ CloudFront has dedicated behavior for /config.js*');
  } else {
    console.log('✗ CloudFront missing /config.js* path pattern');
  }

  // Check for managed_caching_disabled policy for config.js
  const hasConfigPathPattern = terraform.includes('/config.js*');
  const hasCachingDisabledPolicy = terraform.includes('managed_caching_disabled');
  const configSection = terraform.match(/\/config\.js.*?viewer_protocol_policy/s);
  const hasDisabledInConfigSection = configSection && configSection[0].includes('managed_caching_disabled');

  if (hasConfigPathPattern && (hasCachingDisabledPolicy || hasDisabledInConfigSection)) {
    console.log('✓ /config.js* uses Managed-CachingDisabled policy (TTL=0)');
  } else if (hasConfigPathPattern) {
    console.log('⚠ /config.js* path pattern found but caching policy unclear');
  } else {
    console.log('✗ /config.js* path pattern not found');
  }
} else {
  console.log('⚠ Terraform file not found');
}

// ───────────────────────────────────────────────────────────────────────────────
// Check 5: Verify index.html has cache-bust parameter
// ───────────────────────────────────────────────────────────────────────────────

console.log('\nCheck 5: Index.html Script Tag');
console.log('─' .repeat(50));

const htmlPath = path.join(__dirname, '../webapp/frontend/index.html');
if (fs.existsSync(htmlPath)) {
  const html = fs.readFileSync(htmlPath, 'utf8');

  // In source HTML, there should be no cache-bust (added at build time)
  if (html.includes('<script src="/config.js"')) {
    console.log('✓ Source index.html has config.js script tag');
  } else {
    console.log('✗ Source index.html missing config.js script tag');
  }
}

if (fs.existsSync(distConfigPath)) {
  const distHtmlPath = path.join(__dirname, '../webapp/frontend/dist/index.html');
  if (fs.existsSync(distHtmlPath)) {
    const html = fs.readFileSync(distHtmlPath, 'utf8');

    // In dist HTML, cache-bust should be present
    if (html.includes('/config.js?v=')) {
      console.log('✓ Dist index.html has cache-bust parameter: /config.js?v=...');
    } else {
      console.log('⚠ Dist index.html missing cache-bust parameter (may not be built)');
    }
  }
}

// ───────────────────────────────────────────────────────────────────────────────
// Check 6: Verify main.jsx has explicit fetch
// ───────────────────────────────────────────────────────────────────────────────

console.log('\nCheck 6: Runtime Explicit Fetch');
console.log('─' .repeat(50));

const mainJsxPath = path.join(__dirname, '../webapp/frontend/src/main.jsx');
if (fs.existsSync(mainJsxPath)) {
  const mainJsx = fs.readFileSync(mainJsxPath, 'utf8');

  if (mainJsx.includes('fetchConfigExplicitly')) {
    console.log('✓ main.jsx has explicit fetch function');
  } else {
    console.log('✗ main.jsx missing explicit fetch function');
  }

  if (mainJsx.includes("cache: 'no-store'") && mainJsx.includes('Pragma')) {
    console.log('✓ Fetch uses no-cache headers and cache-bypass directives');
  } else {
    console.log('✗ Fetch missing cache-bypass headers');
  }
}

// ───────────────────────────────────────────────────────────────────────────────
// Final Recommendation
// ───────────────────────────────────────────────────────────────────────────────

console.log('\n═══════════════════════════════════════════════════════');
console.log('Recommendations:');
console.log('─' .repeat(50));

const allChecksPass = publicBuildTime && distBuildTime && publicBuildTime === distBuildTime;

if (allChecksPass) {
  console.log('✓ All checks pass - config.js freshness mechanisms are in place');
  console.log('  If experiencing "API 404" errors:');
  console.log('  1. Verify browser Network tab shows config.js returns 200 (not cached)');
  console.log('  2. Check browser DevTools → Application → Storage for config cache');
  console.log('  3. Hard refresh (Ctrl+F5) to bypass browser cache');
  console.log('  4. Verify API_URL in config.js matches current deployment URL');
} else {
  console.log('⚠ Some checks failed or inconclusive:');
  console.log('  1. Run: npm run build:prod');
  console.log('  2. Verify dist/config.js is generated with BUILD_TIME');
  console.log('  3. Re-run this diagnostic');
}

console.log('═══════════════════════════════════════════════════════\n');
