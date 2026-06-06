#!/usr/bin/env node
/**
 * Test the deployed site for errors, console logs, network issues, and auth problems
 */
import { chromium } from 'playwright';
import fs from 'fs';

const CLOUDFRONT_URL = 'https://d2u93283nn45h2.cloudfront.net';
const TIMEOUT = 30000; // 30 seconds
const results = {
  url: CLOUDFRONT_URL,
  timestamp: new Date().toISOString(),
  errors: [],
  warnings: [],
  logs: [],
  network_issues: [],
  auth_issues: [],
  page_load_time: null,
  status_code: null,
  final_url: null,
  page_title: null,
  page_content_sample: null,
  network_requests: [],
};

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  // Capture console messages
  page.on('console', msg => {
    results.logs.push({
      type: msg.type(),
      text: msg.text(),
      location: msg.location(),
    });
    console.log(`[CONSOLE ${msg.type().toUpperCase()}] ${msg.text()}`);
  });

  // Capture page errors
  page.on('pageerror', err => {
    results.errors.push({
      message: err.message,
      stack: err.stack,
      name: err.name,
    });
    console.error(`[PAGE ERROR] ${err.message}`);
  });

  // Capture failed requests
  page.on('requestfailed', request => {
    results.network_issues.push({
      url: request.url(),
      error: request.failure().errorText,
      method: request.method(),
    });
    console.warn(`[REQUEST FAILED] ${request.method()} ${request.url()}: ${request.failure().errorText}`);
  });

  // Capture all requests/responses
  page.on('response', response => {
    if (response.status() >= 400) {
      results.network_issues.push({
        url: response.url(),
        status: response.status(),
        statusText: response.statusText(),
        method: response.request().method(),
      });
      console.warn(`[HTTP ${response.status()}] ${response.request().method()} ${response.url()}`);
    }
    results.network_requests.push({
      url: response.url(),
      status: response.status(),
      method: response.request().method(),
      resourceType: response.request().resourceType(),
    });
  });

  try {
    console.log(`\nAccessing: ${CLOUDFRONT_URL}`);
    const startTime = Date.now();

    const response = await page.goto(CLOUDFRONT_URL, {
      waitUntil: 'networkidle',
      timeout: TIMEOUT,
    });

    results.page_load_time = Date.now() - startTime;
    results.status_code = response?.status();
    results.final_url = page.url();

    console.log(`\n✓ Page loaded in ${results.page_load_time}ms`);
    console.log(`  Status: ${results.status_code}`);
    console.log(`  Final URL: ${results.final_url}`);

    // Get page title and basic content
    results.page_title = await page.title();
    console.log(`  Title: ${results.page_title}`);

    // Get a sample of the page content (first 500 chars of body)
    const bodyText = await page.textContent('body');
    results.page_content_sample = bodyText?.slice(0, 500) || null;

    // Check for Cognito or auth redirects
    if (results.final_url.includes('cognito')) {
      results.auth_issues.push({
        message: 'Page redirected to Cognito',
        final_url: results.final_url,
      });
      console.warn('[AUTH] Page redirected to Cognito - check Cognito configuration');
    }

    // Check localStorage for config
    const config = await page.evaluate(() => {
      try {
        return {
          window_config: typeof window.CONFIG !== 'undefined' ? window.CONFIG : null,
          local_storage: Object.keys(localStorage).reduce((acc, key) => {
            acc[key] = localStorage.getItem(key)?.slice(0, 100) || null;
            return acc;
          }, {}),
        };
      } catch (e) {
        return { error: e.message };
      }
    });
    console.log(`\n  Config check:`, JSON.stringify(config, null, 2));
    results.config = config;

    // Wait a bit for any async operations
    await page.waitForTimeout(2000);

    // Check for React errors
    const reactErrors = await page.evaluate(() => {
      // Check for common React error patterns
      const allText = document.body.innerText;
      return {
        has_error_boundary: allText.includes('Error'),
        has_white_screen: document.body.children.length === 0,
        visible_text_length: allText.length,
      };
    });
    results.react_status = reactErrors;
    console.log(`\n  React Status:`, JSON.stringify(reactErrors, null, 2));

  } catch (error) {
    results.errors.push({
      message: error.message,
      stack: error.stack,
      type: 'Load Error',
    });
    console.error(`\n✗ Failed to load page: ${error.message}`);
  } finally {
    await browser.close();
  }

  // Print summary
  console.log('\n\n========== SUMMARY ==========');
  console.log(`URL: ${results.url}`);
  console.log(`Status Code: ${results.status_code}`);
  console.log(`Page Load Time: ${results.page_load_time}ms`);
  console.log(`Final URL: ${results.final_url}`);
  console.log(`Console Logs: ${results.logs.length}`);
  console.log(`Page Errors: ${results.errors.length}`);
  console.log(`Network Issues: ${results.network_issues.length}`);
  console.log(`Auth Issues: ${results.auth_issues.length}`);
  console.log(`Network Requests: ${results.network_requests.length}`);

  if (results.errors.length > 0) {
    console.log('\n[ERRORS]');
    results.errors.forEach(err => console.log(`  - ${err.message}`));
  }

  if (results.network_issues.length > 0) {
    console.log('\n[NETWORK ISSUES]');
    results.network_issues.forEach(issue => {
      console.log(`  - ${issue.method || 'UNKNOWN'} ${issue.url} (${issue.status || issue.error})`);
    });
  }

  if (results.auth_issues.length > 0) {
    console.log('\n[AUTH ISSUES]');
    results.auth_issues.forEach(issue => console.log(`  - ${issue.message}`));
  }

  // Save detailed results to file
  fs.writeFileSync('test-deployed-site-results.json', JSON.stringify(results, null, 2));
  console.log('\n✓ Detailed results saved to: test-deployed-site-results.json');
})();
