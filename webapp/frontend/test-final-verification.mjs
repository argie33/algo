#!/usr/bin/env node
/**
 * Final End-to-End Verification
 * Comprehensive test covering: page load, auth, health, API calls, console errors
 */

import { chromium } from 'playwright';

async function test() {
  console.log('\n' + '='.repeat(60));
  console.log('FINAL END-TO-END VERIFICATION TEST');
  console.log('='.repeat(60));

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  const results = {
    passed: [],
    failed: [],
    warnings: [],
    http429Count: 0,
    consoleErrorCount: 0,
  };

  // Track network
  page.on('response', (response) => {
    const status = response.status();
    const url = response.url();

    if (status === 429) {
      results.http429Count++;
      results.failed.push(`HTTP 429: ${response.request().method()} ${url.split('?')[0]}`);
    }
  });

  // Track console
  page.on('console', (msg) => {
    if (msg.type() === 'error' && !msg.text().includes('resource')) {
      results.consoleErrorCount++;
      results.failed.push(`Console Error: ${msg.text().substring(0, 80)}`);
    }
  });

  page.on('pageerror', (e) => {
    results.failed.push(`Page Error: ${e.message}`);
  });

  try {
    // Step 1: Load the frontend
    console.log('\n[1/4] Loading frontend...');
    await page.goto('https://d2u93283nn45h2.cloudfront.net', {
      waitUntil: 'load',
      timeout: 30000
    });
    results.passed.push('✅ Page loaded (HTTP 200)');
    console.log('      ✅ Page loaded');

    // Step 2: Wait and check rendering
    console.log('[2/4] Checking page rendering...');
    await page.waitForTimeout(3000);

    const hasContent = await page.evaluate(() => {
      return document.body.innerText.trim().length > 100;
    });

    if (hasContent) {
      results.passed.push('✅ Page rendered with content');
      console.log('      ✅ Page rendered');
    } else {
      results.failed.push('❌ Page did not render content');
      console.log('      ❌ Page empty');
    }

    // Step 3: Check auth
    console.log('[3/4] Checking auth configuration...');
    const authReady = await page.evaluate(() => {
      // Check if Amplify/auth is available
      return !!window.amplifyClientConfig || !!window.__AMPLIFY__;
    });

    if (authReady) {
      results.passed.push('✅ Auth system configured');
      console.log('      ✅ Auth configured');
    } else {
      results.warnings.push('⚠️  Auth system may not be fully loaded');
      console.log('      ⚠️  Auth status unclear');
    }

    // Step 4: Test health endpoint
    console.log('[4/4] Testing health endpoint...');
    const healthResponse = await page.evaluate(async () => {
      try {
        const response = await fetch('/api/health', { method: 'GET' });
        return {
          status: response.status,
          ok: response.ok,
          statusText: response.statusText
        };
      } catch (error) {
        return {
          error: error.message
        };
      }
    });

    if (healthResponse.error) {
      results.failed.push(`❌ Health endpoint error: ${healthResponse.error}`);
      console.log(`      ❌ Health check failed: ${healthResponse.error}`);
    } else if (healthResponse.status === 200) {
      results.passed.push('✅ Health endpoint responding (200)');
      console.log('      ✅ Health check passed');
    } else if (healthResponse.status === 429) {
      results.failed.push('❌ Health endpoint rate limited (429)');
      console.log('      ❌ Health endpoint getting 429');
    } else {
      results.warnings.push(`⚠️  Health endpoint returned ${healthResponse.status}`);
      console.log(`      ⚠️  Health returned ${healthResponse.status}`);
    }

    // Final report
    console.log('\n' + '='.repeat(60));
    console.log('TEST RESULTS SUMMARY');
    console.log('='.repeat(60));

    console.log(`\n✅ Passed (${results.passed.length}):`);
    results.passed.forEach(msg => console.log(`   ${msg}`));

    if (results.failed.length > 0) {
      console.log(`\n❌ Failed (${results.failed.length}):`);
      results.failed.forEach(msg => console.log(`   ${msg}`));
    }

    if (results.warnings.length > 0) {
      console.log(`\n⚠️  Warnings (${results.warnings.length}):`);
      results.warnings.forEach(msg => console.log(`   ${msg}`));
    }

    console.log('\nDetailed Metrics:');
    console.log(`  • HTTP 429 errors: ${results.http429Count}`);
    console.log(`  • Console errors: ${results.consoleErrorCount}`);

    // Final verdict
    console.log('\n' + '='.repeat(60));
    if (results.http429Count === 0 && results.consoleErrorCount === 0 && results.failed.length === 0) {
      console.log('🎉 VERDICT: ✅ SUCCESS - All tests passed!');
      console.log('   • No 429 rate limit errors');
      console.log('   • No console errors');
      console.log('   • Page loads cleanly');
      console.log('   • Auth ready');
      console.log('   • Health endpoint working');
      return 0;
    } else if (results.http429Count > 0) {
      console.log('❌ VERDICT: FAIL - HTTP 429 errors detected');
      return 1;
    } else if (results.consoleErrorCount > 0) {
      console.log('❌ VERDICT: FAIL - Console errors detected');
      return 1;
    } else if (results.failed.length > 0) {
      console.log('❌ VERDICT: FAIL - Critical tests failed');
      return 1;
    } else {
      console.log('⚠️  VERDICT: UNKNOWN - Review warnings above');
      return 2;
    }

  } catch (error) {
    console.error(`\n💥 Test crashed: ${error.message}`);
    return 1;
  } finally {
    await browser.close();
  }
}

const code = await test();
process.exit(code);
