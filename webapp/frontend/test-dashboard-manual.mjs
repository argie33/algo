import { chromium } from '@playwright/test';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  
  try {
    console.log('Loading dashboard on port 5175...');
    await page.goto('http://localhost:5175', { waitUntil: 'load', timeout: 20000 });
    
    // Wait for React to render
    await page.waitForTimeout(2000);
    
    const title = await page.title();
    console.log('✓ Page loaded, title:', title);
    
    // Get visible text
    const text = await page.evaluate(() => {
      const body = document.body.innerText;
      return body.length > 0 ? body.substring(0, 800) : 'NO TEXT CONTENT';
    });
    console.log('\nPage content (first 800 chars):');
    console.log(text);
    
    // Take screenshot
    await page.screenshot({ path: 'dashboard-screenshot.png', fullPage: false });
    console.log('\n✓ Screenshot saved');
    
  } catch (e) {
    console.error('❌ Error:', e.message);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
