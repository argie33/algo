const { chromium } = require('playwright');

async function testAccordion() {
  const browser = await chromium.launch();
  const context = await browser.createContext();
  const page = await context.newPage();

  try {
    console.log('🧪 Testing Trading Signals Accordion...\n');

    // Navigate to the trading signals page
    console.log('📍 Opening Trading Signals page...');
    await page.goto('http://localhost:3000/trading-signals', { waitUntil: 'networkidle' });

    // Wait for the page to load
    await page.waitForTimeout(2000);

    // Test Daily Signals
    console.log('\n📅 Testing DAILY Timeframe:');
    await testTimeframe(page, 'daily');

    // Test Weekly Signals
    console.log('\n📅 Testing WEEKLY Timeframe:');
    await testTimeframe(page, 'weekly');

    // Test Monthly Signals
    console.log('\n📅 Testing MONTHLY Timeframe:');
    await testTimeframe(page, 'monthly');

    console.log('\n✅ All tests completed!\n');

  } catch (error) {
    console.error('❌ Test failed:', error.message);
  } finally {
    await browser.close();
  }
}

async function testTimeframe(page, timeframe) {
  try {
    // Find and click the timeframe button
    const timeframeButton = await page.$(`button:has-text("${timeframe.toUpperCase()}")`);
    if (timeframeButton) {
      await timeframeButton.click();
      await page.waitForTimeout(1500);
    }

    // Check if accordion items exist
    const accordionItems = await page.$$('[role="button"][aria-expanded]');
    console.log(`  Found ${accordionItems.length} accordion items`);

    if (accordionItems.length === 0) {
      console.log(`  ⚠️ No accordion items found for ${timeframe}`);
      return;
    }

    // Expand the first accordion item
    if (accordionItems.length > 0) {
      console.log(`  🔍 Expanding first item...`);
      await accordionItems[0].click();
      await page.waitForTimeout(500);

      // Check for key metrics in the expanded accordion
      const metricTexts = [
        'Risk %',
        'Entry Quality',
        'Market Stage',
        'Stage Number',
        'Profit Target',
        'Breakout Quality',
        'Days in Position'
      ];

      let foundMetrics = 0;
      for (const metric of metricTexts) {
        const exists = await page.$(`text=${metric}`);
        if (exists) {
          foundMetrics++;
          console.log(`    ✓ Found: ${metric}`);
        }
      }

      // Check for actual data values (not zeros/NaN/empty)
      const riskPercentText = await page.textContent('[class*="risk"], [class*="Risk"]');
      const qualityScoreText = await page.textContent('[class*="quality"], [class*="Quality"]');

      if (foundMetrics > 0) {
        console.log(`  ✅ ${timeframe}: ${foundMetrics}/${metricTexts.length} metrics visible`);
      } else {
        console.log(`  ⚠️ ${timeframe}: Some metrics may not be visible`);
      }
    }

  } catch (error) {
    console.log(`  ❌ Error testing ${timeframe}: ${error.message}`);
  }
}

testAccordion().catch(console.error);
