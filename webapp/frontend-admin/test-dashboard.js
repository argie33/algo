import { test, _expect } from '@playwright/test';

test('Portfolio Dashboard - Check for empty values and chart data', async ({ page }) => {
  // Navigate to portfolio dashboard
  await page.goto('http://localhost:5173/portfolio');

  // Wait for the page to load and API calls to complete
  await page.waitForTimeout(3000);

  // Get all metric boxes and their values
  const metrics = await page.locator('[class*="MetricBox"]').all();
  console.log(`Found ${metrics.length} metric boxes`);

  const emptyMetrics = [];
  const populatedMetrics = [];

  for (let i = 0; i < Math.min(metrics.length, 50); i++) {
    const text = await metrics[i].textContent();
    console.log(`Metric ${i}: ${text?.trim()}`);

    if (text?.includes('0') || text?.includes('N/A') || text?.trim() === '') {
      emptyMetrics.push(text);
    } else {
      populatedMetrics.push(text);
    }
  }

  console.log(`\n=== SUMMARY ===`);
  console.log(`Empty/Zero metrics: ${emptyMetrics.length}`);
  console.log(`Populated metrics: ${populatedMetrics.length}`);

  // Check for charts
  const recharts = await page.locator('svg[class*="recharts"]').count();
  console.log(`Found ${recharts} Recharts visualizations`);

  // Check for error messages
  const errors = await page.locator('[role="alert"], [class*="error"], [class*="Error"]').all();
  console.log(`Found ${errors.length} error elements`);

  for (const error of errors) {
    const text = await error.textContent();
    if (text && text.trim()) {
      console.log(`Error: ${text.trim()}`);
    }
  }

  // Get specific card titles and their content
  const cards = await page.locator('[class*="MuiCard"]').all();
  console.log(`\n=== CARD ANALYSIS (first 10) ===`);

  for (let i = 0; i < Math.min(cards.length, 10); i++) {
    const title = await cards[i].locator('[class*="MuiCardHeader"]').textContent();
    const content = await cards[i].textContent();
    const hasCharts = await cards[i].locator('svg').count();

    console.log(`\nCard ${i + 1}: ${title?.trim()}`);
    console.log(`  Charts: ${hasCharts}`);
    console.log(`  Content length: ${content?.length}`);
    console.log(`  Has zeros: ${content?.includes('0.00') ? 'YES' : 'NO'}`);
  }

  // Log first 500 chars of page content
  const pageContent = await page.content();
  console.log(`\n=== PAGE LOAD STATUS ===`);
  console.log(`Page loaded: ${pageContent.length} characters`);
  console.log(`Has recharts library: ${pageContent.includes('recharts') ? 'YES' : 'NO'}`);
  console.log(`Has Material-UI: ${pageContent.includes('mui') ? 'YES' : 'NO'}`);
});
