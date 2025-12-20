import { test, expect } from '@playwright/test';

test('Portfolio Dashboard - Simple data rendering check', async ({ page }) => {
  // Navigate to portfolio dashboard
  await page.goto('http://localhost:5173/portfolio', { waitUntil: 'networkidle' });

  console.log('\n📊 PORTFOLIO DASHBOARD RENDERING TEST\n');
  console.log('=' .repeat(70));

  // Get all page content
  const pageContent = await page.content();
  const textContent = await page.locator('body').textContent() || '';

  // 1. Check for major portfolio symbols
  console.log('\n1️⃣ HOLDINGS VERIFICATION\n');

  const holdings = ['NFLX', 'AAPL', 'BRK', 'NVR', 'CL', 'AVGO', 'NVDA'];
  let holdingsFound = 0;

  for (const symbol of holdings) {
    const found = textContent.includes(symbol);
    console.log(`${found ? '✅' : '❌'} ${symbol}: ${found ? 'Visible' : 'Not visible'}`);
    if (found) holdingsFound++;
  }

  // 2. Check for key metrics
  console.log('\n2️⃣ METRICS VISIBILITY\n');

  const metricsPatterns = [
    { name: 'Returns (negative)', pattern: /-\d+\.\d+%/ },
    { name: 'Portfolio Value', pattern: /\$[\d,]+/ },
    { name: 'Percentages/Weights', pattern: /\d+\.\d+%/ },
    { name: 'Market values', pattern: /\$\d+/ },
  ];

  let metricsFound = 0;
  for (const metric of metricsPatterns) {
    const found = metric.pattern.test(textContent);
    console.log(`${found ? '✅' : '❌'} ${metric.name}: ${found ? 'Found' : 'Not found'}`);
    if (found) metricsFound++;
  }

  // 3. Check for visualizations
  console.log('\n3️⃣ VISUALIZATION ELEMENTS\n');

  const cardCount = await page.locator('[class*="MuiCard"]').count();
  const svgCount = await page.locator('svg').count();
  const chartElements = await page.locator('[class*="recharts"]').count();

  console.log(`✅ Material-UI Cards: ${cardCount}`);
  console.log(`✅ SVG Elements (Charts): ${svgCount}`);
  console.log(`✅ Recharts Elements: ${chartElements}`);

  // 4. Check for error or loading states
  console.log('\n4️⃣ ERROR/LOADING STATES\n');

  const errors = await page.locator('[role="alert"]').count();
  const loading = await page.locator('[class*="loading"], [class*="skeleton"]').count();

  console.log(`${errors === 0 ? '✅' : '❌'} No error alerts: ${errors === 0 ? 'Pass' : `Found ${errors}`}`);
  console.log(`${loading === 0 ? '✅' : '❌'} No loading states: ${loading === 0 ? 'Pass' : `Found ${loading}`}`);

  // 5. Check page performance
  console.log('\n5️⃣ PAGE PERFORMANCE\n');

  const pageSize = pageContent.length;
  console.log(`Page size: ${(pageSize / 1024 / 1024).toFixed(2)}MB (${pageSize} bytes)`);

  // 6. Detailed data check from page text
  console.log('\n6️⃣ KEY DATA POINTS\n');

  // Extract specific values if visible
  const returnMatch = textContent.match(/-\d+\.\d+%/);
  const valueMatch = textContent.match(/\$[\d,]+\.?\d*/);

  if (returnMatch) console.log(`✅ Portfolio Return found: ${returnMatch[0]}`);
  if (valueMatch) console.log(`✅ Portfolio Value found: ${valueMatch[0]}`);

  // 7. Summary
  console.log('\n7️⃣ RENDERING SUMMARY\n');
  console.log('=' .repeat(70));

  const rendererWorking = cardCount > 100 && svgCount > 10;
  const dataLoaded = holdingsFound >= 5 && metricsFound >= 3;

  console.log(`${rendererWorking ? '✅' : '❌'} Dashboard components rendered: ${cardCount} cards, ${svgCount} charts`);
  console.log(`${dataLoaded ? '✅' : '❌'} Data is populated: ${holdingsFound}/7 holdings, ${metricsFound}/4 metric types`);
  console.log(`${errors === 0 ? '✅' : '⚠️'} No errors on page`);

  console.log('\n' + '=' .repeat(70));
  console.log(`\n✅ DASHBOARD RENDERING: ${rendererWorking && dataLoaded ? 'WORKING' : 'HAS ISSUES'}\n`);

  // Basic assertions
  expect(cardCount).toBeGreaterThan(100);
  expect(svgCount).toBeGreaterThan(0);
  expect(errors).toBe(0);
});
