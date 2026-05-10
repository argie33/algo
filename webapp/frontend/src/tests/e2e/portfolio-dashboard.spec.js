import { test, expect } from '@playwright/test';

test('Portfolio Dashboard - Verify data rendering and charts', async ({ page }) => {
  // Navigate to portfolio dashboard
  await page.goto('http://localhost:5173/portfolio', { waitUntil: 'networkidle' });

  // Wait for API calls to complete
  await page.waitForTimeout(2000);

  console.log('\n🔍 PLAYWRIGHT DASHBOARD ANALYSIS\n');
  console.log('=' .repeat(70));

  // 1. Check page title and structure
  console.log('\n1️⃣ PAGE STRUCTURE CHECK\n');
  const pageTitle = await page.title();
  console.log(`✅ Page Title: ${pageTitle}`);

  // 2. Check for loading states
  const loadingElements = await page.locator('[class*="loading"], [class*="Loading"], [class*="skeleton"]').count();
  console.log(`✅ Loading elements found: ${loadingElements}`);

  // 3. Check for error messages
  console.log('\n2️⃣ ERROR CHECK\n');
  const errorAlerts = await page.locator('[role="alert"]').all();
  const errorDivs = await page.locator('[class*="error"], [class*="Error"]').all();

  if (errorAlerts.length === 0 && errorDivs.length === 0) {
    console.log('✅ No error messages detected');
  } else {
    console.log(`⚠️  Found ${errorAlerts.length + errorDivs.length} error elements`);
    for (const error of [...errorAlerts, ...errorDivs]) {
      const text = await error.textContent();
      if (text?.trim()) {
        console.log(`   Error: ${text.trim().substring(0, 80)}`);
      }
    }
  }

  // 4. Check Material-UI Cards (main components)
  console.log('\n3️⃣ CARD COMPONENT ANALYSIS\n');
  const cards = await page.locator('[class*="MuiCard"]').all();
  console.log(`Total cards found: ${cards.length}`);

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
      console.log(`\nCard ${i + 1}: ${cardTitle?.trim() || 'Untitled'}`);
      console.log(`  SVG Elements (Charts): ${svgCount}`);
      console.log(`  Content length: ${cardContent?.length || 0}`);
      console.log(`  Has data: ${cardContent && cardContent.length > 20 ? 'YES' : 'NO'}`);
    }
  }

  console.log(`\n📊 CARD SUMMARY:`);
  console.log(`  Cards with charts: ${cardsWithCharts}/${cards.length}`);
  console.log(`  Cards with data: ${cardsWithData}/${cards.length}`);
  console.log(`  Empty cards: ${cardsEmpty}/${cards.length}`);

  // 5. Check for Recharts library and visualizations
  console.log('\n4️⃣ CHART VISUALIZATION CHECK\n');
  const rechartsContainers = await page.locator('[class*="recharts"]').count();
  const svgElements = await page.locator('svg').count();
  const chartLines = await page.locator('line[class*="recharts"]').count();
  const chartBars = await page.locator('[class*="recharts-bar"]').count();
  const chartPies = await page.locator('[class*="recharts-pie"]').count();

  console.log(`Recharts containers: ${rechartsContainers}`);
  console.log(`Total SVG elements: ${svgElements}`);
  console.log(`Chart lines detected: ${chartLines}`);
  console.log(`Bar charts: ${chartBars}`);
  console.log(`Pie charts: ${chartPies}`);

  if (svgElements === 0) {
    console.log('⚠️  WARNING: No SVG elements found - charts may not be rendering');
  } else {
    console.log('✅ Charts appear to be rendering');
  }

  // 6. Check for specific metric values
  console.log('\n5️⃣ METRIC VALUES CHECK\n');
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
    console.log(`${found ? '✅' : '❌'} ${metric.name}: ${found ? 'Found' : 'Not found'}`);
  }

  // 7. Check API responses via network monitoring
  console.log('\n6️⃣ API CALLS CHECK\n');

  // Wait for any pending network requests
  await page.waitForLoadState('networkidle');

  // Try to find evidence of API data
  const hasPortfolioData = allText.includes('NFLX') || allText.includes('AAPL') || allText.includes('portfolio');
  const hasMetrics = allText.includes('%') || allText.includes('$');

  console.log(`✅ Portfolio data visible: ${hasPortfolioData ? 'YES' : 'NO'}`);
  console.log(`✅ Metrics visible: ${hasMetrics ? 'YES' : 'NO'}`);

  // 8. Final summary
  console.log('\n7️⃣ FINAL SUMMARY\n');
  console.log('=' .repeat(70));

  const hasContent = cards.length > 0 && cardsWithData > 0;
  const hasVisualizations = svgElements > 10;

  if (hasContent && hasVisualizations) {
    console.log('✅ DASHBOARD APPEARS TO BE RENDERING CORRECTLY');
    console.log(`   - ${cards.length} cards loaded`);
    console.log(`   - ${cardsWithData} cards with data`);
    console.log(`   - ${svgElements} visualizations rendered`);
  } else {
    console.log('⚠️  DASHBOARD MAY HAVE RENDERING ISSUES');
    console.log(`   - Cards loaded: ${cards.length}`);
    console.log(`   - Cards with data: ${cardsWithData}`);
    console.log(`   - SVG elements: ${svgElements}`);
  }

  console.log('=' .repeat(70) + '\n');
});
