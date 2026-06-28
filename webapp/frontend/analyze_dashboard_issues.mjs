import { chromium } from 'playwright';
import fs from 'fs';

async function analyzeDashboard() {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    const issues = [];

    page.on('response', response => {
      if (response.status() >= 400) {
        issues.push({
          type: 'API_ERROR',
          status: response.status(),
          url: response.url(),
          method: response.request().method()
        });
      }
    });

    page.on('console', msg => {
      if (msg.type() === 'error') {
        issues.push({
          type: 'CONSOLE_ERROR',
          text: msg.text()
        });
      }
    });

    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto('http://localhost:5173', { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(5000);

    // Find all panels with error/unavailable states
    const panelHeaders = await page.locator('[class*="card-head"], h2, h3').allTextContents();
    console.log('=== DASHBOARD PANELS ===\n');
    const uniquePanels = [...new Set(panelHeaders.map(h => h.trim()))].filter(h => h.length > 0);
    uniquePanels.slice(0, 20).forEach(p => console.log(`  • ${p}`));

    // Look for specific error messages
    const errorSelectors = [
      ':has-text("unavailable")',
      ':has-text("error")',
      ':has-text("failed")',
      '[role="alert"]',
      '[class*="error-message"]',
      '[class*="unavailable"]'
    ];

    console.log('\n=== UNAVAILABLE/ERROR INDICATORS ===\n');
    for (const selector of errorSelectors) {
      const elements = await page.locator(selector).all();
      for (const elem of elements) {
        const text = await elem.textContent();
        if (text && text.trim().length > 5) {
          console.log(`✗ ${text.trim().substring(0, 100)}`);
          issues.push({
            type: 'UI_ERROR',
            text: text.trim()
          });
        }
      }
    }

    // Check for missing data patterns
    console.log('\n=== CHECKING SPECIFIC PANELS ===\n');

    // Market Trends (known issue with ? icon)
    const marketTrendsPanel = await page.locator('text=Market Trends').first();
    if (await marketTrendsPanel.isVisible()) {
      const parent = marketTrendsPanel.locator('..');
      const content = await parent.textContent();
      console.log(`Market Trends: ${content?.includes('unavailable') ? '❌ UNAVAILABLE' : '✓ Available'}`);
    }

    // Take screenshot of the issue area
    const issueElement = await page.locator(':has-text("instructional")').first();
    if (await issueElement.isVisible()) {
      await issueElement.screenshot({ path: 'issue_market_trends.png' });
      console.log('\nScreenshot of Market Trends issue saved');
    }

    // Scroll down to check more panels
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight / 2));
    await page.waitForTimeout(2000);

    console.log('\n=== API CALLS MADE ===\n');
    const apiCalls = new Set();
    page.on('response', response => {
      if (response.url().includes('/api/')) {
        const status = response.status();
        const url = response.url().replace(/https?:\/\/[^/]+/, '');
        apiCalls.add(`${status} ${url}`);
      }
    });

    await page.waitForTimeout(1000);
    Array.from(apiCalls).forEach(call => console.log(`  ${call}`));

    console.log('\n=== SUMMARY ===\n');
    console.log(`Found ${issues.length} issues:`);
    issues.forEach((issue, idx) => {
      console.log(`${idx + 1}. [${issue.type}] ${issue.text || issue.url || issue.status}`);
    });

    // Save full page screenshot
    await page.screenshot({ path: 'dashboard_full_analysis.png', fullPage: true });
    console.log('\nFull dashboard screenshot saved to dashboard_full_analysis.png');

  } finally {
    await browser.close();
  }
}

analyzeDashboard().catch(console.error);
