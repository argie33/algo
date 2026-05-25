import { test, Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

/**
 * Diagnostic test to check production site F12 DevTools logs
 * Captures: console logs, network requests, errors, config.js content
 *
 * Run: npx playwright test diagnose-production.spec.ts --headed
 */

test.describe('Production Site Diagnostics', () => {
  let page: Page;
  const logs: { type: string; message: string; timestamp: string }[] = [];
  const networkRequests: { method: string; url: string; status?: number; response?: string }[] = [];
  const errors: string[] = [];

  test.beforeEach(async ({ browser }) => {
    // Create new page with listener setup
    page = await browser.newPage();

    // Capture all console messages
    page.on('console', (msg) => {
      logs.push({
        type: msg.type(),
        message: msg.text(),
        timestamp: new Date().toISOString(),
      });
      console.log(`[${msg.type().toUpperCase()}] ${msg.text()}`);
    });

    // Capture page errors
    page.on('pageerror', (err) => {
      errors.push(err.toString());
      console.error(`[ERROR] ${err}`);
    });

    // Capture network requests
    page.on('response', (response) => {
      networkRequests.push({
        method: response.request().method(),
        url: response.url(),
        status: response.status(),
      });
      console.log(`[${response.status()}] ${response.request().method()} ${response.url()}`);
    });

    // Capture request failures
    page.on('requestfailed', (request) => {
      errors.push(`Request failed: ${request.url()}`);
      console.error(`[FAILED] ${request.url()}`);
    });
  });

  test('Check production CloudFront deployment', async () => {
    // Get URL from environment or use localhost
    const baseUrl = process.env.PRODUCTION_URL || 'http://localhost:5173';
    console.log(`\n🌐 Testing: ${baseUrl}\n`);

    try {
      // Navigate to site
      console.log('📍 Navigating to site...');
      const response = await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
      console.log(`✅ Navigation status: ${response?.status()}`);

      // Wait a bit for config.js to load and API calls to start
      await page.waitForTimeout(2000);

      // Check window.__CONFIG__
      console.log('\n📋 Checking window.__CONFIG__...');
      const config = await page.evaluate(() => {
        return (window as any).__CONFIG__;
      });
      console.log('Config:', JSON.stringify(config, null, 2));

      if (!config) {
        errors.push('window.__CONFIG__ is undefined - config.js not loaded!');
        console.error('❌ window.__CONFIG__ is undefined');
      } else {
        console.log('✅ window.__CONFIG__ loaded');
        if (!config.API_URL) {
          errors.push('API_URL not set in config');
          console.error('❌ API_URL missing in config');
        } else {
          console.log(`✅ API_URL: ${config.API_URL}`);
        }
      }

      // Check if there's an axios instance
      console.log('\n🔗 Checking axios API client...');
      const apiBaseURL = await page.evaluate(() => {
        return (window as any).api?.defaults?.baseURL || 'not found';
      });
      console.log(`API baseURL: ${apiBaseURL}`);

      // Try to fetch from API
      console.log('\n🧪 Testing API endpoint...');
      const apiUrl = config?.API_URL || 'http://localhost:5173';
      try {
        const healthResponse = await page.evaluate(async (url: string) => {
          try {
            const res = await fetch(`${url}/api/health`);
            return {
              status: res.status,
              ok: res.ok,
              headers: Object.fromEntries(res.headers.entries()),
              body: await res.json(),
            };
          } catch (e) {
            return { error: (e as Error).message };
          }
        }, apiUrl);
        console.log('Health check result:', JSON.stringify(healthResponse, null, 2));
      } catch (e) {
        console.error(`❌ Health check failed: ${e}`);
      }

      // Take screenshot
      console.log('\n📸 Taking screenshot...');
      const screenshotPath = path.join('test-results', 'production-diagnostics.png');
      fs.mkdirSync(path.dirname(screenshotPath), { recursive: true });
      await page.screenshot({ path: screenshotPath });
      console.log(`✅ Screenshot saved: ${screenshotPath}`);

    } catch (err) {
      errors.push(`Navigation/test error: ${err}`);
      console.error(`❌ Test error: ${err}`);
    }

    // Generate diagnostic report
    console.log('\n' + '='.repeat(60));
    console.log('DIAGNOSTIC REPORT');
    console.log('='.repeat(60));

    console.log(`\n📊 Console Logs (${logs.length})`);
    logs.forEach((log) => {
      console.log(`  [${log.type}] ${log.message}`);
    });

    console.log(`\n🌐 Network Requests (${networkRequests.length})`);
    networkRequests.slice(0, 20).forEach((req) => {
      console.log(`  [${req.status || '?'}] ${req.method} ${req.url}`);
    });

    console.log(`\n⚠️  Errors (${errors.length})`);
    errors.forEach((err) => {
      console.log(`  • ${err}`);
    });

    // Save detailed report to file
    const reportPath = path.join('test-results', 'production-diagnostics.json');
    fs.mkdirSync(path.dirname(reportPath), { recursive: true });
    fs.writeFileSync(
      reportPath,
      JSON.stringify(
        {
          timestamp: new Date().toISOString(),
          url: process.env.PRODUCTION_URL || 'http://localhost:5173',
          logs,
          networkRequests,
          errors,
          summary: {
            totalLogs: logs.length,
            totalRequests: networkRequests.length,
            totalErrors: errors.length,
            hasConfig: logs.some((l) => l.message.includes('__CONFIG__')),
            criticalIssues: errors.length > 0,
          },
        },
        null,
        2
      )
    );
    console.log(`\n📄 Detailed report saved: ${reportPath}`);

    // Assertions
    if (errors.length > 0) {
      console.log(`\n❌ Found ${errors.length} errors - review above`);
    } else {
      console.log('\n✅ No critical errors detected');
    }
  });

  test.afterEach(async () => {
    await page?.close();
  });
});
