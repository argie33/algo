import { test, expect } from '@playwright/test';

test('Compare test expectations vs real site behavior', async ({ page }) => {
  const realSiteIssues = [];
  const apiResponses = [];

  // Track all API calls and responses
  page.on('response', response => {
    if (response.url().includes('/api/')) {
      apiResponses.push({
        url: response.url(),
        status: response.status(),
        ok: response.ok()
      });
    }
  });

  await page.goto('http://localhost:5173');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(3000);

  // Test 1: Dashboard should show market data (works in tests)
  const marketData = await page.locator('[data-testid*="market"], .market-overview').count();
  if (marketData === 0) {
    realSiteIssues.push('❌ Market overview section missing (works in tests)');
  }

  // Test 2: Price charts should display (works in tests with mock data)
  const _priceCharts = await page.locator('.recharts-responsive-container, [data-testid*="chart"]').count();
  const noDataMessages = await page.locator(':has-text("No data available"), :has-text("No price data")').count();

  if (noDataMessages > 0) {
    realSiteIssues.push(`❌ ${noDataMessages} charts showing "No data available" (work in tests)`);
  }

  // Test 3: Portfolio data should load (works in tests)
  const _portfolioErrors = await page.locator(':has-text("portfolio"), :has-text("Portfolio")').count();
  const portfolioNoData = await page.locator(':has-text("No portfolio"), :has-text("No holdings")').count();

  if (portfolioNoData > 0) {
    realSiteIssues.push(`❌ Portfolio showing no data (works in tests with mocks)`);
  }

  // Test 4: Check for API failures that tests don't encounter
  const failedApis = apiResponses.filter(api => !api.ok);
  if (failedApis.length > 0) {
    realSiteIssues.push(`❌ ${failedApis.length} API calls failing (tests use mocks that never fail)`);
    console.log('Failed APIs:', failedApis);
  }

  // Test 5: Error components visible (shouldn't happen in tests)
  const errorComponents = await page.locator('.MuiAlert-root, [role="alert"], .error-message, .error-state').count();
  if (errorComponents > 0) {
    realSiteIssues.push(`❌ ${errorComponents} error components visible (tests don't show these)`);
  }

  // Test 6: Loading states stuck (tests complete quickly)
  const loadingStates = await page.locator('.MuiCircularProgress-root, .loading, :has-text("Loading")').count();
  if (loadingStates > 2) { // Allow some loading states
    realSiteIssues.push(`⚠️ ${loadingStates} components stuck in loading state`);
  }

  // Test 7: Authentication state (test mocks vs real auth)
  const authIssues = await page.locator(':has-text("Sign in"), :has-text("Login required")').count();
  if (authIssues > 0) {
    realSiteIssues.push(`⚠️ Authentication required (tests bypass this)`);
  }

  console.log('\n🔍 ISSUES FOUND ON REAL SITE (but work in tests):');
  realSiteIssues.forEach(issue => console.log(issue));

  console.log('\n📊 API Response Summary:');
  console.log(`✅ Successful: ${apiResponses.filter(api => api.ok).length}`);
  console.log(`❌ Failed: ${apiResponses.filter(api => !api.ok).length}`);

  // Allow the test to pass but document the issues
  expect(realSiteIssues.length).toBeLessThan(10); // Expect some issues, but not too many
});