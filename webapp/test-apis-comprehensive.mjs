#!/usr/bin/env node
/**
 * Comprehensive API Testing - Core Dashboard APIs
 */

const API_BASE = process.env.API_URL || 'http://localhost:3001';
const TIMEOUT = 10000;

const colors = {
  reset: '\x1b[0m',
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  cyan: '\x1b[36m',
};

const log = {
  ok: (msg) => console.log(`${colors.green}[OK]${colors.reset} ${msg}`),
  error: (msg) => console.log(`${colors.red}[ERROR]${colors.reset} ${msg}`),
  warn: (msg) => console.log(`${colors.yellow}[WARN]${colors.reset} ${msg}`),
  info: (msg) => console.log(`${colors.cyan}[INFO]${colors.reset} ${msg}`),
};

async function testApiEndpoint(path, description = '') {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), TIMEOUT);

    const response = await fetch(`${API_BASE}${path}`, {
      method: 'GET',
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json' },
    });

    clearTimeout(timeoutId);

    const status = response.status;
    const isOk = status >= 200 && status < 300;
    const statusMsg = `${status} ${response.statusText}`;
    const fullMsg = description ? `${description}: ${statusMsg}` : `${path}: ${statusMsg}`;

    if (isOk) {
      log.ok(fullMsg);
      return { ok: true, status };
    } else {
      log.error(fullMsg);
      return { ok: false, status };
    }
  } catch (error) {
    const errorMsg = error.name === 'AbortError' ? 'TIMEOUT' : error.message;
    log.error(`${description || path}: ${errorMsg}`);
    return { ok: false, error: errorMsg };
  }
}

async function main() {
  console.log('\n' + '='.repeat(70));
  console.log('DASHBOARD API TEST SUITE');
  console.log('='.repeat(70));
  log.info(`API Base: ${API_BASE}\n`);

  const endpoints = [
    // Core Health & Status
    { path: '/api/health', desc: 'Health Check', required: true },
    { path: '/api', desc: 'API Root', required: true },

    // Stock Market Data (CORE)
    { path: '/api/stocks?limit=10', desc: 'List Stocks', required: true },
    { path: '/api/prices/history/AAPL?limit=50', desc: 'Stock Price History (AAPL)', required: true },
    { path: '/api/prices/history/SPY?limit=50', desc: 'ETF Price History (SPY)', required: true },

    // Fundamentals & Earnings (IMPORTANT)
    { path: '/api/earnings?symbol=AAPL', desc: 'Earnings Calendar (AAPL)', required: true },

    // Market Analysis (CORE)
    { path: '/api/economic', desc: 'Economic Data', required: true },
    { path: '/api/sentiment', desc: 'Market Sentiment', required: true },
    { path: '/api/market', desc: 'Market Health', required: true },
    { path: '/api/sectors', desc: 'Sector Analysis', required: true },

    // Trading Signals (CORE)
    { path: '/api/signals', desc: 'Trading Signals', required: true },
    { path: '/api/scores', desc: 'Stock Scores', required: true },
  ];

  let passed = 0, failed = 0;
  let requiredFailed = false;

  for (const endpoint of endpoints) {
    const result = await testApiEndpoint(endpoint.path, endpoint.desc);
    if (result.ok) {
      passed++;
    } else {
      failed++;
      if (endpoint.required) requiredFailed = true;
    }
  }

  console.log('\n' + '='.repeat(70));
  console.log(`RESULTS: ${colors.green}${passed} passed${colors.reset}, ${colors.red}${failed} failed${colors.reset}`);

  if (requiredFailed) {
    log.error('Some REQUIRED APIs are failing');
    console.log('='.repeat(70) + '\n');
    process.exit(1);
  } else {
    log.ok('All required APIs are operational');
    console.log('='.repeat(70) + '\n');
    process.exit(0);
  }
}

main().catch(err => {
  log.error(`Fatal error: ${err.message}`);
  process.exit(1);
});
