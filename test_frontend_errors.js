#!/usr/bin/env node

/**
 * Frontend Error Diagnostic Test
 * Uses Playwright to test the frontend and capture all errors
 */

const { chromium } = require('/home/arger/algo/webapp/frontend/node_modules/@playwright/test');
const fs = require('fs');
const path = require('path');

async function runDiagnostics() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const errors = [];
  const warnings = [];
  const networkErrors = [];
  const requests = [];
  const responses = [];

  // Capture console messages
  page.on('console', msg => {
    const text = msg.text();
    const args = msg.args();

    if (msg.type() === 'error') {
      errors.push({
        type: 'CONSOLE_ERROR',
        message: text,
        location: msg.location()
      });
    } else if (msg.type() === 'warning') {
      warnings.push({
        type: 'CONSOLE_WARNING',
        message: text
      });
    }

    console.log(`[${msg.type().toUpperCase()}]`, text);
  });

  // Capture page errors
  page.on('pageerror', error => {
    errors.push({
      type: 'PAGE_ERROR',
      message: error.message,
      stack: error.stack
    });
    console.error('[PAGE_ERROR]', error.message);
  });

  // Capture network errors
  page.on('response', response => {
    responses.push({
      url: response.url(),
      status: response.status(),
      statusText: response.statusText()
    });

    if (!response.ok() && response.url().includes('api')) {
      networkErrors.push({
        type: 'API_ERROR',
        url: response.url(),
        status: response.status(),
        statusText: response.statusText()
      });
      console.error('[API_ERROR]', response.status(), response.url());
    }
  });

  page.on('request', request => {
    requests.push({
      method: request.method(),
      url: request.url(),
      resourceType: request.resourceType()
    });
  });

  try {
    console.log('\n═══════════════════════════════════════════════════════════');
    console.log('🔍 FRONTEND ERROR DIAGNOSTIC TEST');
    console.log('═══════════════════════════════════════════════════════════\n');

    // Try different URLs to test
    const urlsToTest = [
      'http://localhost:3000',
      'http://localhost:5173',
      'http://localhost:5174',
    ];

    let frontendUrl = null;

    for (const url of urlsToTest) {
      try {
        console.log(`\n⏳ Testing ${url}...`);
        const response = await page.goto(url, {
          waitUntil: 'networkidle',
          timeout: 10000
        });

        if (response && response.ok()) {
          console.log(`✅ Frontend found at ${url}`);
          frontendUrl = url;
          break;
        }
      } catch (e) {
        console.log(`❌ Not available at ${url}`);
      }
    }

    if (!frontendUrl) {
      console.log('\n❌ Frontend not running on any standard port!');
      console.log('\nTried:');
      urlsToTest.forEach(url => console.log(`  - ${url}`));

      await browser.close();

      const report = {
        status: 'FRONTEND_NOT_FOUND',
        message: 'Frontend is not running on any standard port',
        urls_tested: urlsToTest,
        error_count: 0,
        warning_count: 0,
        network_errors: []
      };

      reportResults(report);
      return;
    }

    // Wait for page to load
    console.log('\n⏳ Waiting for page to fully load...');
    await page.waitForLoadState('networkidle').catch(() => {
      console.log('⚠️  Network did not stabilize, continuing anyway...');
    });

    await page.waitForTimeout(2000);

    // Check for specific elements
    console.log('\n🔍 Checking page content...');

    const hasMainContent = await page.locator('main, [role="main"]').count() > 0;
    const hasNavigation = await page.locator('nav, [role="navigation"]').count() > 0;
    const hasErrors = errors.length > 0;
    const hasApiErrors = networkErrors.length > 0;

    console.log(`  Main content present: ${hasMainContent ? '✅' : '❌'}`);
    console.log(`  Navigation present: ${hasNavigation ? '✅' : '❌'}`);

    // Get page title
    const title = await page.title();
    console.log(`  Page title: ${title}`);

    // Get current URL
    const currentUrl = page.url();
    console.log(`  Current URL: ${currentUrl}`);

    // Take screenshot
    console.log('\n📸 Taking screenshot...');
    const screenshotPath = '/tmp/frontend-test-screenshot.png';
    await page.screenshot({ path: screenshotPath });
    console.log(`  Screenshot saved: ${screenshotPath}`);

    // Export HTML
    const htmlPath = '/tmp/frontend-test-page.html';
    const html = await page.content();
    fs.writeFileSync(htmlPath, html);
    console.log(`  Page HTML saved: ${htmlPath}`);

    // Analyze API calls
    console.log('\n📡 Network Analysis:');
    console.log(`  Total requests: ${requests.length}`);

    const apiRequests = requests.filter(r => r.url.includes('api') || r.url.includes('http'));
    console.log(`  API requests: ${apiRequests.length}`);

    if (apiRequests.length > 0) {
      console.log('\n  API Requests Made:');
      apiRequests.forEach((req, idx) => {
        console.log(`    ${idx + 1}. ${req.method} ${req.url}`);
      });
    }

    // Get response status codes
    console.log('\n  Response Status Codes:');
    const statusCodes = {};
    responses.forEach(r => {
      const code = r.status;
      statusCodes[code] = (statusCodes[code] || 0) + 1;
    });
    Object.entries(statusCodes).forEach(([code, count]) => {
      const status = code >= 200 && code < 300 ? '✅' : code >= 300 && code < 400 ? '⚠️' : '❌';
      console.log(`    ${status} ${code}: ${count} requests`);
    });

    // Report results
    const report = {
      status: 'DIAGNOSTIC_COMPLETE',
      timestamp: new Date().toISOString(),
      frontend_url: frontendUrl,
      page_title: title,
      current_url: currentUrl,
      has_main_content: hasMainContent,
      has_navigation: hasNavigation,
      error_count: errors.length,
      warning_count: warnings.length,
      network_error_count: networkErrors.length,
      api_request_count: apiRequests.length,
      total_requests: requests.length,
      errors: errors.slice(0, 10), // First 10 errors
      warnings: warnings.slice(0, 5),
      network_errors: networkErrors.slice(0, 10),
      api_requests: apiRequests.slice(0, 10),
      response_codes: statusCodes,
      screenshots: {
        page: screenshotPath,
        html: htmlPath
      }
    };

    reportResults(report);

  } catch (error) {
    console.error('\n❌ TEST FAILED:', error.message);

    const report = {
      status: 'TEST_ERROR',
      error: error.message,
      stack: error.stack
    };

    reportResults(report);
  } finally {
    await browser.close();
  }
}

function reportResults(report) {
  console.log('\n═══════════════════════════════════════════════════════════');
  console.log('📊 DIAGNOSTIC REPORT');
  console.log('═══════════════════════════════════════════════════════════\n');

  if (report.status === 'FRONTEND_NOT_FOUND') {
    console.log('❌ FRONTEND NOT RUNNING');
    console.log('\nThe frontend application is not accessible.');
    console.log('\nTo start the frontend locally:');
    console.log('  cd /home/arger/algo/webapp/frontend');
    console.log('  npm run dev');
    return;
  }

  if (report.status === 'TEST_ERROR') {
    console.log('❌ TEST ERROR:', report.error);
    return;
  }

  console.log(`Frontend URL: ${report.frontend_url}`);
  console.log(`Page Title: ${report.page_title}`);
  console.log(`Current URL: ${report.current_url}`);

  console.log(`\nPage Content:`);
  console.log(`  Main content: ${report.has_main_content ? '✅' : '❌'}`);
  console.log(`  Navigation: ${report.has_navigation ? '✅' : '❌'}`);

  console.log(`\nErrors Detected:`);
  console.log(`  Console errors: ${report.error_count}`);
  console.log(`  Console warnings: ${report.warning_count}`);
  console.log(`  Network errors: ${report.network_error_count}`);

  if (report.errors.length > 0) {
    console.log(`\nTop Errors:`);
    report.errors.forEach((err, idx) => {
      console.log(`  ${idx + 1}. [${err.type}] ${err.message.substring(0, 80)}`);
    });
  }

  if (report.network_errors.length > 0) {
    console.log(`\nNetwork Errors:`);
    report.network_errors.forEach((err, idx) => {
      console.log(`  ${idx + 1}. [${err.status}] ${err.url}`);
    });
  }

  console.log(`\nNetwork Summary:`);
  console.log(`  Total requests: ${report.total_requests}`);
  console.log(`  API requests: ${report.api_request_count}`);
  console.log(`  Response codes:`, report.response_codes);

  if (report.api_requests.length > 0) {
    console.log(`\nAPI Requests:`);
    report.api_requests.forEach((req, idx) => {
      console.log(`  ${idx + 1}. ${req.method} ${req.url.substring(0, 80)}`);
    });
  }

  console.log(`\nArtifacts:`);
  console.log(`  Screenshot: ${report.screenshots.page}`);
  console.log(`  Page HTML: ${report.screenshots.html}`);

  // Save report to file
  const reportPath = '/tmp/frontend-diagnostic-report.json';
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
  console.log(`  Full report: ${reportPath}`);

  console.log('\n═══════════════════════════════════════════════════════════\n');

  // Summary
  if (report.error_count === 0 && report.network_error_count === 0) {
    console.log('✅ NO ERRORS DETECTED - Frontend is working!');
  } else if (report.error_count > 0 || report.network_error_count > 0) {
    console.log(`⚠️  ERRORS DETECTED - See details above`);
  }
}

// Run the test
runDiagnostics().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
