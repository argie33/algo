const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext();
  const page = await context.newPage();

  const issues = [];

  page.on('console', msg => {
    if (msg.type() === 'error') {
      console.log(`🔴 CONSOLE ERROR: ${msg.text()}`);
      issues.push(msg.text());
    }
  });

  page.on('pageerror', error => {
    console.log(`🔴 PAGE ERROR: ${error.message}`);
    issues.push(error.message);
  });

  try {
    console.log('Loading /app/markets...\n');
    await page.goto('http://localhost:5173/app/markets', { waitUntil: 'load' });
    
    // Wait for React to fully render (check for main-content class)
    await page.waitForSelector('.main-content, .empty, .card', { timeout: 10000 });
    
    console.log('✅ Page loaded and React rendered\n');

    // Get page state
    const pageState = await page.evaluate(() => {
      const content = document.body.innerText;
      const hasError = content.toLowerCase().includes('failed') || content.toLowerCase().includes('error') ||
                       content.includes('Cannot read') || content.includes('undefined');
      return {
        hasContent: content.length > 100,
        hasError,
        contentPreview: content.substring(0, 200),
        title: document.title
      };
    });

    console.log('Page Title:', pageState.title);
    console.log('Has Content:', pageState.hasContent);
    console.log('Has Errors:', pageState.hasError);
    console.log('\nContent Preview:');
    console.log(pageState.contentPreview);
    console.log('\n' + '='.repeat(60));

    if (pageState.hasContent && !pageState.hasError) {
      console.log('\n✅ PAGE IS WORKING!\n');
    } else {
      console.log('\n⚠️ PAGE LOADED BUT MIGHT HAVE ISSUES\n');
    }

  } catch (error) {
    console.log(`\n❌ ERROR: ${error.message}\n`);
  }

  // Keep browser open for 3 seconds to see the page
  await page.waitForTimeout(3000);
  await browser.close();
})();
