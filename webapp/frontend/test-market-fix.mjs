import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  
  await page.goto('http://localhost:5174/app/market', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(3000);
  
  const status = await page.evaluate(() => ({
    title: document.querySelector('h1')?.textContent,
    h2s: Array.from(document.querySelectorAll('h2')).slice(0, 5).map(h => h.textContent),
    contentLength: document.body.innerText.length,
    hasCircleProgress: document.querySelector('[class*="CircularProgress"]') !== null,
    cards: document.querySelectorAll('[class*="MuiCard"]').length,
    tables: document.querySelectorAll('table').length
  }));
  
  console.log('=== Market Overview After Fix ===');
  console.log(JSON.stringify(status, null, 2));
  
  await browser.close();
})();
