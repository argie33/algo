#!/usr/bin/env node
/**
 * Basic Frontend Test - Check page accessibility
 */

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';
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

const pages = [
  { path: '/', name: 'Home / Market Overview' },
  { path: '/stocks', name: 'Stock Market' },
  { path: '/economic', name: 'Economic Dashboard' },
  { path: '/signals', name: 'Trading Signals' },
  { path: '/sectors', name: 'Sector Analysis' },
];

async function testPage(path, name) {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), TIMEOUT);

    const response = await fetch(`${FRONTEND_URL}${path}`, {
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    const status = response.status;
    const isOk = status >= 200 && status < 400;

    if (isOk) {
      log.ok(`${name} (${path}): ${status} OK`);
      return { ok: true, page: name };
    } else {
      log.error(`${name} (${path}): ${status} Error`);
      return { ok: false, page: name };
    }
  } catch (error) {
    const errorMsg = error.name === 'AbortError' ? 'TIMEOUT' : error.message;
    log.error(`${name} (${path}): ${errorMsg}`);
    return { ok: false, page: name };
  }
}

async function main() {
  console.log('\n' + '='.repeat(70));
  console.log('FRONTEND ACCESSIBILITY TEST');
  console.log('='.repeat(70));
  log.info(`Frontend: ${FRONTEND_URL}\n`);

  let passed = 0, failed = 0;

  for (const page of pages) {
    const result = await testPage(page.path, page.name);
    if (result.ok) passed++;
    else failed++;
  }

  console.log('\n' + '='.repeat(70));
  console.log(`RESULTS: ${colors.green}${passed} passed${colors.reset}, ${colors.red}${failed} failed${colors.reset}`);

  if (failed === 0) {
    log.ok('All pages are accessible');
  }
  console.log('='.repeat(70) + '\n');

  process.exit(failed === 0 ? 0 : 1);
}

main().catch(err => {
  log.error(`Test error: ${err.message}`);
  process.exit(1);
});
