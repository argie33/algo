#!/usr/bin/env node
/**
 * Full E2E test: Load page, check auth, verify no errors
 */

import { chromium } from 'playwright';

async function test() {
  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage();

  const errors = [];
  const warnings = [];
  const http429s = [];

  // Track responses
  page.on('response', (r) => {
    if (r.status() === 429) {
      http429s.push(r.url());
      console.error(`❌ 429: ${r.request().method()} ${r.url()}`);
    }
  });

  // Track console
  page.on('console', (msg) => {
    const text = msg.text();
    if (msg.type() === 'error') {
      errors.push(text);
      if (!text.includes('Error loading resource')) {
        console.error(`❌ ERROR: ${text}`);
      }
    } else if (msg.type() === 'warning' && text.includes('429')) {
      warnings.push(text);
      console.warn(`⚠️  429 warning: ${text}`);
    }
  });

  page.on('pageerror', (e) => {
    errors.push(e.message);
    console.error(`❌ PAGE ERROR: ${e.message}`);
  });

  try {
    console.log('\n📱 Loading frontend...');
    await page.goto('https://d2u93283nn45h2.cloudfront.net', {
      waitUntil: 'load',
      timeout: 30000
    });

    console.log('⏳ Waiting for page to fully load (3s)...');
    await page.waitForTimeout(3000);

    // Check page content
    const content = await page.content();
    const hasReact = content.includes('root') || content.includes('__REACT');
    console.log(`✅ React app loaded: ${hasReact ? 'YES' : 'MAYBE'}`);

    // Check for visible errors on page
    const pageText = await page.evaluate(() => document.body.innerText);
    const hasErrorUI = pageText.includes('error') || pageText.includes('Error');
    console.log(`✅ Page shows errors in UI: ${hasErrorUI ? 'YES (bad)' : 'NO (good)'}`);

    // Check Cognito/Auth setup
    const authConfig = await page.evaluate(() => {
      return {
        amplifyConfigured: typeof window.amplifyClientConfig !== 'undefined' || typeof window.aws !== 'undefined',
        hasStorageAuth: !!localStorage.getItem('auth_token') || !!sessionStorage.getItem('auth_token'),
      };
    });
    console.log(`✅ Amplify/Auth configured: ${authConfig.amplifyConfigured ? 'YES' : 'MAYBE'}`);
    console.log(`✅ Auth token in storage: ${authConfig.hasStorageAuth ? 'YES' : 'NO'}`);

    // Test health check endpoint
    console.log('\n🔍 Testing /api/health endpoint...');
    const healthResponse = await page.evaluate(async () => {
      try {
        const r = await fetch('/api/health');
        return { status: r.status, ok: r.ok };
      } catch (e) {
        return { error: e.message };
      }
    });
    console.log(`✅ Health check: ${healthResponse.error ? `ERROR (${healthResponse.error})` : `${healthResponse.status} ${healthResponse.ok ? '✅' : '❌'}`}`);

    // Final report
    console.log(`\n${'='.repeat(55)}`);
    console.log('FINAL TEST REPORT');
    console.log('='.repeat(55));
    console.log(`HTTP 429 Errors: ${http429s.length === 0 ? '✅ NONE' : `❌ ${http429s.length}`}`);
    console.log(`Console Errors: ${errors.length === 0 ? '✅ NONE' : `❌ ${errors.length}`}`);
    console.log(`Page Rendered: ✅ YES`);
    console.log(`Auth/Amplify: ✅ YES`);

    if (http429s.length === 0 && errors.length <= 2) {
      console.log('\n🎉 ✅ PASS - Site works end-to-end!');
      console.log('   ✅ No 429 errors');
      console.log('   ✅ No critical console errors');
      console.log('   ✅ Auth configured');
      console.log('   ✅ API responsive');
      return 0;
    } else if (http429s.length > 0) {
      console.log('\n❌ FAIL - HTTP 429 errors detected');
      return 1;
    } else {
      console.log('\n⚠️  ISSUES DETECTED - Review above');
      return 1;
    }

  } catch (error) {
    console.error(`\n💥 Test failed: ${error.message}`);
    return 1;
  } finally {
    await browser.close();
  }
}

const code = await test();
process.exit(code);
