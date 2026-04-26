import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  
  let apiCalls = [];
  page.on('response', resp => {
    if (resp.url().includes('/api/')) {
      apiCalls.push({
        status: resp.status(),
        url: resp.url().substring(resp.url().indexOf('/api/')),
        ok: resp.status() < 400
      });
    }
  });
  
  await page.goto('http://localhost:5174/app/market', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2000);
  
  const content = await page.evaluate(() => ({
    title: document.querySelector('h1')?.textContent,
    h2s: Array.from(document.querySelectorAll('h2')).map(h => h.textContent),
    bodyText: document.body.innerText.substring(0, 500),
    errorElements: Array.from(document.querySelectorAll('[class*="error"]')).length,
    emptyElements: Array.from(document.querySelectorAll('[class*="empty"]')).length
  }));
  
  console.log('=== Market Overview Page ===');
  console.log('Title:', content.title);
  console.log('H2 Headings:', content.h2s);
  console.log('Body text:', content.bodyText);
  console.log('API Calls:');
  apiCalls.forEach(api => {
    console.log(`  ${api.status} ${api.url}`);
  });

  await browser.close();
})();
