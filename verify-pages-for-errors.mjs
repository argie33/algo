#!/usr/bin/env node
/**
 * Simple HTML-based error detection
 * Fetches each page and checks the HTML for React error boundaries, error text, etc.
 */

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

const colors = {
  reset: '\x1b[0m',
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  cyan: '\x1b[36m',
};

const log = {
  ok: (msg) => console.log(`${colors.green}✓${colors.reset} ${msg}`),
  error: (msg) => console.log(`${colors.red}✗${colors.reset} ${msg}`),
  warn: (msg) => console.log(`${colors.yellow}⚠${colors.reset} ${msg}`),
  info: (msg) => console.log(`${colors.cyan}ℹ${colors.reset} ${msg}`),
};

const pages = [
  { path: '/', name: 'Home / Market Overview' },
  { path: '/stocks', name: 'Stock Market' },
  { path: '/economic', name: 'Economic Dashboard' },
  { path: '/signals', name: 'Trading Signals' },
  { path: '/sectors', name: 'Sector Analysis' },
];

async function checkPageForErrors(path, name) {
  try {
    const url = `${FRONTEND_URL}${path}`;
    const response = await fetch(url, {
      timeout: 10000,
      headers: { 'Accept': 'text/html' }
    });

    if (!response.ok) {
      log.error(`${name} (${path}): HTTP ${response.status}`);
      return { ok: false, page: name, error: `HTTP ${response.status}` };
    }

    const html = await response.text();

    // Check for React error boundary indicators
    const hasErrorBoundary = html.includes('error') &&
                            (html.includes('Error Boundary') ||
                             html.includes('Something went wrong'));

    // Check for common error patterns
    const errorPatterns = [
      /Error:\s+/i,
      /Uncaught/i,
      /failed.*fetch/i,
      /not found.*404/i,
      /internal server error/i,
    ];

    const hasVisibleError = errorPatterns.some(pattern => {
      // Only check in visible text areas, not HTML attributes
      const textOnly = html.replace(/<[^>]*>/g, ' ');
      return pattern.test(textOnly) && textOnly.length > 50;
    });

    // Check that page has reasonable content
    const textContent = html.replace(/<[^>]*>/g, ' ');
    const contentLength = textContent.trim().length;
    const hasContent = contentLength > 200; // Minimal content check

    if (!hasContent) {
      log.warn(`${name}: Page loaded but appears empty (${contentLength} chars)`);
      return { ok: false, page: name, error: 'No content' };
    }

    if (hasVisibleError || hasErrorBoundary) {
      log.error(`${name}: Error text detected in page content`);
      return { ok: false, page: name, error: 'Error detected' };
    }

    log.ok(`${name}: Loaded successfully, no visible errors`);
    return { ok: true, page: name, contentSize: contentLength };

  } catch (error) {
    log.error(`${name}: ${error.message}`);
    return { ok: false, page: name, error: error.message };
  }
}

async function main() {
  console.log('\n' + '='.repeat(70));
  console.log('DASHBOARD PAGE VERIFICATION');
  console.log('='.repeat(70));
  log.info(`Frontend: ${FRONTEND_URL}`);
  log.info(`Checking each page for React errors and error indicators\n`);

  const results = [];
  let allOk = true;

  for (const page of pages) {
    const result = await checkPageForErrors(page.path, page.name);
    results.push(result);
    if (!result.ok) allOk = false;
  }

  // Summary
  console.log('\n' + '='.repeat(70));
  console.log('VERIFICATION RESULTS');
  console.log('='.repeat(70));

  const passed = results.filter(r => r.ok).length;
  const failed = results.filter(r => !r.ok).length;

  results.forEach(result => {
    if (result.ok) {
      console.log(`${colors.green}✓${colors.reset} ${result.page}`);
    } else {
      console.log(`${colors.red}✗${colors.reset} ${result.page}: ${result.error}`);
    }
  });

  console.log('\n' + '='.repeat(70));
  console.log(`Pages passed: ${colors.green}${passed}/5${colors.reset}`);

  if (allOk) {
    log.ok('All dashboard pages verified - no error indicators found');
    console.log('\n' + colors.green + '✅ PAGES VERIFIED - Ready for F12 console inspection' + colors.reset);
  } else {
    log.error(`${failed} page(s) have issues`);
  }

  console.log('='.repeat(70));
  console.log('\nNext Step: Open browser F12 console to manually verify logs are clean');
  console.log(`Visit: ${FRONTEND_URL}`);
  console.log('Press: F12 → Console tab');
  console.log('Check: 0 red errors on each page\n');

  process.exit(allOk ? 0 : 1);
}

main().catch(err => {
  log.error(`Fatal error: ${err.message}`);
  process.exit(1);
});
