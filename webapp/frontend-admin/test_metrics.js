const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const context = await browser.createBrowserContext();
  const page = await context.newPage();

  try {
    console.log('🌐 Navigating to stock detail page for ACN...');
    await page.goto('http://localhost:5173/stocks/ACN', { waitUntil: 'networkidle', timeout: 30000 });
    
    // Wait for the page to load metrics
    await page.waitForTimeout(3000);
    
    console.log('✅ Page loaded');
    
    // Get all text from the page
    const pageText = await page.textContent('body');
    
    // Search for key metrics
    console.log('\n📊 Checking for metrics...');
    
    const checks = [
      { name: 'ACN stock symbol', pattern: /ACN/i, found: pageText.match(/ACN/i) },
      { name: 'ROE ~25.51%', pattern: /25\.5/, found: pageText.match(/25\.5/) },
      { name: 'ROE ~11.18%', pattern: /11\.18/, found: pageText.match(/11\.18/) },
      { name: 'NOT decimal 0.2551', pattern: /0\.2551/, found: pageText.match(/0\.2551/) },
    ];
    
    checks.forEach(check => {
      if (check.name.startsWith('NOT')) {
        if (check.found) {
          console.log('❌', check.name, '- ERROR: Found old decimal format!');
        } else {
          console.log('✅', check.name);
        }
      } else {
        if (check.found) {
          console.log('✅', check.name);
        } else {
          console.log('⚠️ ', check.name, '- NOT FOUND');
        }
      }
    });
    
    // Take screenshot
    console.log('\n📸 Taking screenshot...');
    await page.screenshot({ path: '/tmp/stock-detail.png', fullPage: true });
    console.log('✅ Screenshot saved to /tmp/stock-detail.png');
    
  } catch (error) {
    console.error('❌ Error:', error.message);
  } finally {
    await browser.close();
  }
})();
