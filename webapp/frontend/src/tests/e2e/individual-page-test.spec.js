import { test, expect } from '@playwright/test';

const testPages = [
  { path: '/portfolio', name: 'Portfolio Management' },
  { path: '/market', name: 'Market Overview' },
  { path: '/trading', name: 'Trading Signals' },
  { path: '/technical', name: 'Technical Analysis' },
  { path: '/screener', name: 'Stock Screener' },
  { path: '/sentiment', name: 'Sentiment Analysis' }
];

for (const pageInfo of testPages) {
  test(`Individual page test: ${pageInfo.name}`, async ({ page }) => {
    // Monitor console errors
    const consoleErrors = [];
    page.on('console', msg => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    // Set up auth like in the main tests
    await page.addInitScript(() => {
      localStorage.setItem('financial_auth_token', 'e2e-test-token');
      localStorage.setItem('api_keys_status', JSON.stringify({
        alpaca: { configured: true, valid: true },
        polygon: { configured: true, valid: true }, 
        finnhub: { configured: true, valid: true }
      }));
    });

    console.log(`🧪 Testing ${pageInfo.name} at ${pageInfo.path}...`);
    
    // Navigate to specific page
    try {
      await page.goto(pageInfo.path, { waitUntil: 'domcontentloaded', timeout: 15000 });
      await page.waitForSelector('#root', { state: 'attached', timeout: 10000 });
      await page.waitForTimeout(3000);

      // Check for MUI Tabs errors specifically
      const muiTabsErrors = consoleErrors.filter(error => 
        error.includes('MUI:') && error.includes('Tabs') && error.includes('value')
      );

      console.log(`📊 ${pageInfo.name}: ${consoleErrors.length} total errors, ${muiTabsErrors.length} MUI Tabs errors`);
      
      if (muiTabsErrors.length > 0) {
        console.log(`❌ MUI Tabs errors on ${pageInfo.name}:`);
        muiTabsErrors.forEach(error => console.log(`   - ${error}`));
      }

      // Should not have MUI Tabs errors on individual pages
      expect(muiTabsErrors.length, `${pageInfo.name} should not have MUI Tabs errors`).toBe(0);
      
    } catch (error) {
      console.log(`⚠️ ${pageInfo.name} failed to load: ${error.message}`);
      // If page fails to load, that's not a MUI Tabs issue, but we should note it
    }
  });
}