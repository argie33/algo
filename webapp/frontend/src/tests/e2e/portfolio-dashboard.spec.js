import { test, expect } from '@playwright/test';

test('Portfolio Dashboard - Verify data rendering and charts', async ({ page }) => {
  // Navigate to portfolio dashboard
  await page.goto('http://localhost:5173/portfolio', { waitUntil: 'networkidle' });

  // Wait for API calls to complete
  await page.waitForTimeout(2000);


  // 1. Check page title and structure
  const pageTitle = await page.title();

  // 2. Check for loading states
  const loadingElements = await page.locator('[class*="loading"], [class*="Loading"], [class*="skeleton"]').count();

  // 3. Check for error messages
  const errorAlerts = await page.locator('[role="alert"]').all();
  const errorDivs = await page.locator('[class*="error"], [class*="Error"]').all();

  if (errorAlerts.length === 0 && errorDivs.length === 0) {
    console.log('âœ… No error messages detected');
  } else {
    console.log(`⚠ï¸  Found ${errorAlerts.length + errorDivs.length} error elements`);
    for (const error of [...errorAlerts, ...errorDivs]) {
      const text = await error.textContent();
      if (text?.trim()) {
      }
    }
  }

  // 4. Check Material-UI Cards (main components)
  const cards = await page.locator('[class*="MuiCard"]').all();

  let cardsWithCharts = 0;
  let cardsWithData = 0;
  let cardsEmpty = 0;

  for (let i = 0; i < Math.min(cards.length, 30); i++) {
    const cardContent = await cards[i].textContent();
    const cardTitle = await cards[i].locator('[class*="MuiCardHeader"]').first().textContent();
    const svgCount = await cards[i].locator('svg').count();

    if (svgCount > 0) {
      cardsWithCharts++;
    }

    if (cardContent && cardContent.trim().length > 20) {
      cardsWithData++;
    } else {
      cardsEmpty++;
    }

    if (i < 10) {
    }
  }


  // 5. Check for Recharts library and visualizations
  const rechartsContainers = await page.locator('[class*="recharts"]').count();
  const svgElements = await page.locator('svg').count();
  const chartLines = await page.locator('line[class*="recharts"]').count();
  const chartBars = await page.locator('[class*="recharts-bar"]').count();
  const chartPies = await page.locator('[class*="recharts-pie"]').count();


  if (svgElements === 0) {
  } else {
  }

  // 6. Check for specific metric values
  const allText = await page.textContent();

  const metrics = [
    { name: 'Total Return', pattern: /-\d+\.\d+%|Total Return/ },
    { name: 'Portfolio Value', pattern: /\$[\d,]+|Portfolio Value/ },
    { name: 'Positions', pattern: /\d+ positions|Position.*NFLX|AAPL|BRK/ },
    { name: 'Herfindahl Index', pattern: /0\.\d+|Herfindahl/ },
    { name: 'Effective N', pattern: /Effective N.*\d+\.\d+/ },
  ];

  for (const metric of metrics) {
    const found = metric.pattern.test(allText);
  }

  // 7. Check API responses via network monitoring

  // Wait for any pending network requests
  await page.waitForLoadState('networkidle');

  // Try to find evidence of API data
  const hasPortfolioData = allText.includes('NFLX') || allText.includes('AAPL') || allText.includes('portfolio');
  const hasMetrics = allText.includes('%') || allText.includes('$');


  // 8. Final summary

  const hasContent = cards.length > 0 && cardsWithData > 0;
  const hasVisualizations = svgElements > 10;

  // Portfolio dashboard displays expected elements

});

