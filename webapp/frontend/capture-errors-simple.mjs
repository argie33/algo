import { chromium } from 'playwright';
import fs from 'fs';

const RESULTS = {
  consoleErrors: [],
  consoleWarnings: [],
  networkErrors: [],
  pageErrors: [],
};

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  // Track all console messages
  page.on('console', (msg) => {
    const logData = {
      type: msg.type(),
      text: msg.text(),
      location: msg.location(),
    };

    if (msg.type() === 'error') {
      RESULTS.consoleErrors.push(logData);
      console.error(`[CONSOLE ERROR] ${msg.text()}`);
    } else if (msg.type() === 'warning') {
      RESULTS.consoleWarnings.push(logData);
      console.warn(`[CONSOLE WARNING] ${msg.text()}`);
    }
  });

  // Track page errors
  page.on('pageerror', (error) => {
    RESULTS.pageErrors.push({
      message: error.message,
      stack: error.stack?.split('\n')[0],
    });
    console.error(`[PAGE ERROR] ${error.message}`);
  });

  // Track network errors
  page.on('response', (response) => {
    if (response.status() >= 400) {
      const errorData = {
        status: response.status(),
        url: response.url(),
        statusText: response.statusText(),
      };
      if (response.status() >= 500) {
        RESULTS.networkErrors.push(errorData);
        console.error(`[5xx ERROR] ${response.status()} ${response.url()}`);
      }
    }
  });

  // Track request failures
  page.on('requestfailed', (request) => {
    RESULTS.networkErrors.push({
      url: request.url(),
      failure: request.failure().errorText,
    });
    console.error(`[REQUEST FAILED] ${request.url()} - ${request.failure().errorText}`);
  });

  console.log('🔍 Starting error capture from localhost:5173...\n');

  try {
    console.log('📍 Navigating to http://localhost:5173...');
    const response = await page.goto('http://localhost:5173', {
      waitUntil: 'networkidle',
      timeout: 15000
    }).catch(err => {
      console.warn(`⚠️ Navigation completed with: ${err.message}`);
      return null;
    });

    // Wait for dynamic content and errors
    console.log('⏳ Waiting 5 seconds for errors and dynamic content...');
    await page.waitForTimeout(5000);

    // Try to capture more specific errors by checking the page
    const title = await page.title();
    const url = page.url();
    console.log(`\n📄 Page title: ${title}`);
    console.log(`📄 Current URL: ${url}`);

    // Check for specific error elements or states
    const bodyHTML = await page.locator('body').innerHTML().catch(() => '');
    const hasConfigError = bodyHTML.includes('__CONFIG_ERROR__');
    const hasError = bodyHTML.toLowerCase().includes('error');

    console.log(`\n📊 CAPTURE RESULTS:\n`);
    console.log(`✓ Console Errors: ${RESULTS.consoleErrors.length}`);
    RESULTS.consoleErrors.forEach((e, i) => {
      console.log(`  ${i + 1}. ${e.text.substring(0, 100)}`);
    });

    console.log(`✓ Console Warnings: ${RESULTS.consoleWarnings.length}`);
    RESULTS.consoleWarnings.slice(0, 3).forEach((e, i) => {
      console.log(`  ${i + 1}. ${e.text.substring(0, 100)}`);
    });

    console.log(`✓ Network 5xx Errors: ${RESULTS.networkErrors.length}`);
    RESULTS.networkErrors.slice(0, 10).forEach((e, i) => {
      console.log(`  ${i + 1}. ${e.status || 'FAILED'} ${e.url}`);
    });

    console.log(`✓ Page Errors: ${RESULTS.pageErrors.length}`);
    RESULTS.pageErrors.slice(0, 5).forEach((e, i) => {
      console.log(`  ${i + 1}. ${e.message}`);
    });

    console.log(`\n🔧 Page State:`);
    console.log(`  Config Error Present: ${hasConfigError}`);
    console.log(`  HTML Contains 'error': ${hasError}`);

    // Save results
    fs.writeFileSync('error-capture-results.json', JSON.stringify(RESULTS, null, 2));
    console.log('\n✅ Full results saved to error-capture-results.json');

    // Take a screenshot
    await page.screenshot({ path: 'frontend-screenshot.png', fullPage: false });
    console.log('📷 Screenshot saved to frontend-screenshot.png');
  } catch (error) {
    console.error('❌ Capture error:', error.message);
  } finally {
    await browser.close();
  }
})();
