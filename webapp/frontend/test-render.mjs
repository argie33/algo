import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  
  await page.goto('http://localhost:5174/app/trading-signals', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  
  const pageContent = await page.evaluate(() => {
    // Get all visible text
    const text = document.body.innerText;
    
    // Look for specific elements
    const title = document.querySelector('h1')?.textContent;
    const tables = Array.from(document.querySelectorAll('table')).length;
    const cards = Array.from(document.querySelectorAll('[class*="card"], [class*="Card"]')).length;
    const buyButtons = Array.from(document.querySelectorAll('button, span')).filter(el => 
      el.textContent.toUpperCase().includes('BUY')
    ).length;
    
    // Check for error messages
    const errorElements = Array.from(document.querySelectorAll('*')).filter(el => 
      el.textContent.toLowerCase().includes('error') || 
      el.textContent.toLowerCase().includes('failed') ||
      el.textContent.toLowerCase().includes('no signals')
    ).map(el => el.textContent.substring(0, 100));
    
    return {
      title,
      textLength: text.length,
      tables,
      cards,
      buyCount: buyButtons,
      errors: errorElements.slice(0, 3),
      textSample: text.substring(0, 300)
    };
  });
  
  console.log('=== Page Content Analysis ===');
  console.log(JSON.stringify(pageContent, null, 2));

  await browser.close();
})();
