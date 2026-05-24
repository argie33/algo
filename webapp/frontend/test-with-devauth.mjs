#!/usr/bin/env node
import { chromium } from 'playwright';

const PORT = 5173;
const BASE_URL = `http://localhost:${PORT}`;

const PAGES = [
  '/app/sectors',
  '/app/signals',
  '/app/scores',
];

async function test() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();

  for (const pagePath of PAGES) {
    const page = await context.newPage();
    const pageErrors = [];
    const apiCalls = [];

    page.on('console', msg => {
      if (msg.type() === 'error') {
        pageErrors.push(msg.text());
      }
    });

    page.on('response', response => {
      if (response.url().includes('/api')) {
        apiCalls.push({
          url: response.url(),
          status: response.status(),
        });
      }
    });

    try {
      console.log(`\n🧪 Testing ${pagePath} with devAuth...`);

      const url = `${BASE_URL}${pagePath}`;

      // Inject devAuth session BEFORE navigating
      await page.goto(`${BASE_URL}/`, { waitUntil: 'domcontentloaded', timeout: 15000 });

      await page.evaluate(() => {
        // Set up devAuth session
        sessionStorage.setItem('devAuth_session', JSON.stringify({
          username: 'dev-admin',
          email: 'admin@dev.local',
          firstName: 'Dev',
          lastName: 'Admin'
        }));

        // Set up auth token
        const token = 'devToken.eyJzdWIiOiJkZXYtYWRtaW4iLCJpYXQiOjE2NzQyMDAwMDAsImV4cCI6MTY3NDIwMzYwMH0=.sig';
        sessionStorage.setItem('authToken', token);
        sessionStorage.setItem('idToken', token);
      });

      // Now navigate to the actual page
      await page.goto(url, { waitUntil: 'load', timeout: 15000 });
      await page.waitForTimeout(2000);

      console.log(`  ✅ Page loaded (${pageErrors.length} console errors)`);
      console.log(`  📡 API calls made: ${apiCalls.length}`);

      if (apiCalls.length > 0) {
        console.log('  API Responses:');
        apiCalls.forEach(call => {
          const status = call.status === 200 ? '✅' : '⚠️';
          console.log(`    ${status} ${call.status} - ${call.url.split('?')[0]}`);
        });
      }

      if (pageErrors.length > 0) {
        console.log('  Errors:');
        pageErrors.forEach(err => {
          console.log(`    ❌ ${err.slice(0, 100)}`);
        });
      }

    } catch (error) {
      console.error(`  ❌ ERROR: ${error.message}`);
    } finally {
      await page.close();
    }
  }

  await browser.close();
}

test();
