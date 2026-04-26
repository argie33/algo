import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  
  const pages = [
    { name: 'Dashboard', path: '/app/market' },
    { name: 'Economic', path: '/app/economic' },
    { name: 'Sectors', path: '/app/sectors' },
    { name: 'Earnings', path: '/app/earnings' },
    { name: 'Financials', path: '/app/financial-data' },
    { name: 'Deep Value', path: '/app/deep-value' },
    { name: 'Signals', path: '/app/trading-signals' },
    { name: 'ETF Signals', path: '/app/etf-signals' },
    { name: 'Scores', path: '/app/scores' },
    { name: 'Sentiment', path: '/app/sentiment' },
    { name: 'Commodities', path: '/app/commodities' }
  ];

  console.log('=== FINAL PAGE STATUS ===\n');
  
  for (const p of pages) {
    await page.goto(`http://localhost:5174${p.path}`, { waitUntil: 'domcontentloaded', timeout: 5000 }).catch(() => null);
    await page.waitForTimeout(1500);
    
    const status = await page.evaluate(() => {
      const text = document.body.innerText.toLowerCase();
      const title = document.querySelector('h1')?.textContent || 'N/A';
      const tables = document.querySelectorAll('table tr').length;
      const loading = document.querySelector('[class*="CircularProgress"]') !== null;
      
      return { title, tables, loading, content: text.length };
    });
    
    const icon = status.loading ? '⏳' : (status.content > 500 ? '✅' : '⚠️');
    console.log(`${icon} ${p.name.padEnd(15)} | Title: ${status.title?.substring(0, 20) || 'N/A'} | Tables: ${status.tables} | Content: ${status.content}`);
  }

  await browser.close();
})();
