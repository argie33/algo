#!/usr/bin/env node
import { chromium } from 'playwright';

const PORT = 5173;
const BASE_URL = `http://localhost:${PORT}`;

async function testPageErrors() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const consoleMessages = [];
  const networkErrors = [];
  const apiCalls = [];

  page.on('console', msg => {
    consoleMessages.push({
      type: msg.type(),
      text: msg.text(),
      location: msg.location(),
    });
  });

  page.on('response', response => {
    if (response.status() >= 400) {
      networkErrors.push({
        url: response.url(),
        status: response.status(),
        statusText: response.statusText(),
      });
    }
    if (response.url().includes('/api')) {
      apiCalls.push({
        url: response.url(),
        status: response.status(),
      });
    }
  });

  try {
    console.log(`\n🧪 Testing /app/sectors with detailed error logging...\n`);

    await page.goto(`${BASE_URL}/app/sectors`, { waitUntil: 'load', timeout: 15000 });
    await page.waitForTimeout(3000);

    // Get console errors
    const errors = consoleMessages.filter(m => m.type === 'error');
    const warnings = consoleMessages.filter(m => m.type === 'warning');

    console.log(`📊 CONSOLE STATISTICS:`);
    console.log(`  Total messages: ${consoleMessages.length}`);
    console.log(`  Errors: ${errors.length}`);
    console.log(`  Warnings: ${warnings.length}`);

    if (errors.length > 0) {
      console.log(`\n🔴 CONSOLE ERRORS (${errors.length}):`);
      const uniqueErrors = {};
      errors.forEach((err, i) => {
        const msg = err.text.slice(0, 120);
        if (!uniqueErrors[msg]) {
          uniqueErrors[msg] = [];
        }
        uniqueErrors[msg].push(i);
      });

      Object.entries(uniqueErrors).forEach(([msg, indices], idx) => {
        console.log(`  ${idx + 1}. (${indices.length}x) ${msg}`);
      });
    }

    if (networkErrors.length > 0) {
      console.log(`\n⚠️ NETWORK ERRORS (${networkErrors.length}):`);
      const uniqueNetErrors = {};
      networkErrors.forEach(err => {
        const key = `${err.status} ${err.url.split('?')[0].split('/').slice(-1)[0]}`;
        if (!uniqueNetErrors[key]) {
          uniqueNetErrors[key] = 0;
        }
        uniqueNetErrors[key]++;
      });

      Object.entries(uniqueNetErrors).forEach(([key, count]) => {
        console.log(`  ${key}: ${count}x`);
      });
    }

    if (apiCalls.length > 0) {
      console.log(`\n📡 API CALLS (${apiCalls.length}):`);
      const apiErrors = apiCalls.filter(c => c.status >= 400);
      console.log(`  Success: ${apiCalls.length - apiErrors.length}`);
      console.log(`  Errors: ${apiErrors.length}`);
      if (apiErrors.length > 0) {
        apiErrors.forEach(call => {
          console.log(`    ❌ ${call.status} - ${call.url.split('/api')[1] || call.url}`);
        });
      }
    }

    // Check if devAuth is initialized
    const authState = await page.evaluate(() => {
      return {
        hasDevSession: !!sessionStorage.getItem('devAuth_session'),
        hasAuthToken: !!sessionStorage.getItem('authToken'),
        hasIdToken: !!sessionStorage.getItem('idToken'),
      };
    });

    console.log(`\n🔐 AUTH STATE:`);
    console.log(`  devAuth session: ${authState.hasDevSession ? '✅' : '❌'}`);
    console.log(`  authToken: ${authState.hasAuthToken ? '✅' : '❌'}`);
    console.log(`  idToken: ${authState.hasIdToken ? '✅' : '❌'}`);

  } catch (error) {
    console.error('\n❌ Test failed:', error.message);
  } finally {
    await context.close();
    await browser.close();
  }
}

testPageErrors();
