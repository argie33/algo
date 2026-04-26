import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  
  const pages = [
    { name: 'Dashboard', path: '/app/market' },
    { name: 'Economic', path: '/app/economic' },
    { name: 'Sectors', path: '/app/sectors' },
    { name: 'Sentiment', path: '/app/sentiment' },
    { name: 'Earnings', path: '/app/earnings' },
    { name: 'Financials', path: '/app/financial-data' },
    { name: 'Deep Value', path: '/app/deep-value' },
    { name: 'Signals', path: '/app/trading-signals' },
    { name: 'ETF Signals', path: '/app/etf-signals' },
    { name: 'Scores', path: '/app/scores' },
    { name: 'Commodities', path: '/app/commodities' },
    { name: 'Portfolio', path: '/app/portfolio' },
    { name: 'Optimizer', path: '/app/optimizer' },
    { name: 'Trades', path: '/app/trades' }
  ];

  console.log('\n=== FULL PAGE TEST REPORT ===\n');
  
  for (const p of pages) {
    try {
      const start = Date.now();
      await page.goto(`http://localhost:5173${p.path}`, { waitUntil: 'domcontentloaded', timeout: 6000 }).catch(() => null);
      const loadTime = Date.now() - start;
      await page.waitForTimeout(1500);
      
      const status = await page.evaluate(() => {
        const text = document.body.innerText;
        return {
          title: document.querySelector('h1')?.textContent || 'N/A',
          hasContent: text.length > 100,
          hasError: text.toLowerCase().includes('error') && !text.toLowerCase().includes('unauthorized'),
          hasLoading: document.querySelector('[class*="CircularProgress"]') !== null,
          tables: document.querySelectorAll('table tr').length,
          charts: document.querySelectorAll('canvas, svg[data-name*="chart"]').length
        };
      });
      
      const icon = status.hasError ? '❌' : (status.hasLoading ? '⏳' : (status.hasContent ? '✅' : '⚠️'));
      console.log(`${icon} ${p.name.padEnd(15)} | Load: ${loadTime}ms | Tables: ${status.tables} | Has content: ${status.hasContent} | Title: ${status.title?.substring(0, 20) || 'N/A'}`);
      
    } catch (err) {
      console.log(`❌ ${p.name.padEnd(15)} | ERROR: ${err.message.substring(0, 50)}`);
    }
  }

  await browser.close();
})();
