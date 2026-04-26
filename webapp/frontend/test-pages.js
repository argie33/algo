const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  
  const pages = [
    { name: 'Dashboard', url: 'http://localhost:5174/' },
    { name: 'Stocks', url: 'http://localhost:5174/stocks' },
    { name: 'Trading Signals', url: 'http://localhost:5174/signals' },
    { name: 'Earnings', url: 'http://localhost:5174/earnings' },
    { name: 'Financials', url: 'http://localhost:5174/financials' },
    { name: 'Sectors', url: 'http://localhost:5174/sectors' }
  ];

  for (const p of pages) {
    console.log(`\n=== ${p.name} ===`);
    try {
      await page.goto(p.url, { waitUntil: 'domcontentloaded', timeout: 5000 }).catch(() => null);
      await page.waitForTimeout(1000);
      
      const status = await page.evaluate(() => {
        const text = document.body.innerText;
        return {
          hasContent: text.length > 100,
          hasError: text.toLowerCase().includes('error') || text.toLowerCase().includes('failed'),
          hasLoadingText: text.includes('Loading') || text.includes('loading'),
          rowCount: document.querySelectorAll('table tr').length
        };
      });
      
      console.log(JSON.stringify(status));
    } catch (err) {
      console.log('TIMEOUT or ERROR:', err.message.split('\n')[0]);
    }
  }

  await browser.close();
})();
