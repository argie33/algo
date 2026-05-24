import { test, expect } from '@playwright/test';

test('Portfolio Dashboard - Simple data rendering check', async ({ page }) => {
  // Navigate to portfolio dashboard
  await page.goto('http://localhost:5173/portfolio', { waitUntil: 'networkidle' });


  // Get all page content
  const pageContent = await page.content();
  const textContent = await page.locator('body').textContent() || '';

  // 1. Check for major portfolio symbols (actual holdings in test portfolio)

  const holdings = ['GOOGL', 'AMZN', 'META', 'NVDA', 'NFLX', 'MSFT', 'AAPL', 'TSLA', 'AMD', 'JNJ'];
  let holdingsFound = 0;

  for (const symbol of holdings) {
    const found = textContent.includes(symbol);
    if (found) holdingsFound++;
  }

  // 2. Check for key metrics

  const metricsPatterns = [
    { name: 'Returns (negative)', pattern: /-\d+\.\d+%/ },
    { name: 'Portfolio Value', pattern: /\$[\d,]+/ },
    { name: 'Percentages/Weights', pattern: /\d+\.\d+%/ },
    { name: 'Market values', pattern: /\$\d+/ },
  ];

  let metricsFound = 0;
  for (const metric of metricsPatterns) {
    const found = metric.pattern.test(textContent);
    if (found) metricsFound++;
  }

  // 3. Check for visualizations

  const cardCount = await page.locator('[class*="MuiCard"]').count();
  const svgCount = await page.locator('svg').count();
  const chartElements = await page.locator('[class*="recharts"]').count();


  // 4. Check for error or loading states

  const errors = await page.locator('[role="alert"]').count();
  const loading = await page.locator('[class*="loading"], [class*="skeleton"]').count();

  console.log(`${errors === 0 ? 'âœ…' : 'âŒ'} No error alerts: ${errors === 0 ? 'Pass' : `Found ${errors}`}`);

  // 5. Check page performance

  const pageSize = pageContent.length;

  // 6. Detailed data check from page text

  // Extract specific values if visible
  const returnMatch = textContent.match(/-\d+\.\d+%/);
  const valueMatch = textContent.match(/\$[\d,]+\.?\d*/);

  if (returnMatch) console.log(`âœ… Portfolio Return found: ${returnMatch[0]}`);
  if (valueMatch) console.log(`âœ… Portfolio Value found: ${valueMatch[0]}`);

  // 7. Summary

  const rendererWorking = cardCount > 100 && svgCount > 10;
  const dataLoaded = holdingsFound >= 5 && metricsFound >= 3;

  console.log(`${errors === 0 ? 'âœ…' : 'âš ï¸'} No errors on page`);


  // Basic assertions - all 10 holdings should render
  expect(holdingsFound).toBeGreaterThanOrEqual(9); // At least 9 of 10 holdings visible
  expect(cardCount).toBeGreaterThan(100);
  expect(svgCount).toBeGreaterThan(0);
  expect(errors).toBe(0);
});

