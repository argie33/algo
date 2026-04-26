import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  
  const pages = [
    { name: 'Market Overview', path: '/app/market' },
    { name: 'Economic Dashboard', path: '/app/economic' },
    { name: 'Sector Analysis', path: '/app/sectors' },
    { name: 'Earnings Calendar', path: '/app/earnings' },
    { name: 'Financial Data', path: '/app/financial-data' },
    { name: 'Deep Value', path: '/app/deep-value' },
    { name: 'Trading Signals', path: '/app/trading-signals' },
    { name: 'ETF Signals', path: '/app/etf-signals' },
    { name: 'Stock Scores', path: '/app/scores' },
    { name: 'Sentiment', path: '/app/sentiment' },
    { name: 'Commodities', path: '/app/commodities' }
  ];

  console.log('=== PAGE DATA STATUS ===\n');
  
  for (const p of pages) {
    try {
      await page.goto(`http://localhost:5174${p.path}`, { waitUntil: 'domcontentloaded', timeout: 5000 }).catch(() => null);
      await page.waitForTimeout(1500);
      
      const status = await page.evaluate(() => {
        const text = document.body.innerText.toLowerCase();
        const hasError = text.includes('error') || text.includes('failed') || text.includes('no data') || text.includes('no results');
        const tableRows = document.querySelectorAll('table tr').length;
        const hasCards = document.querySelectorAll('[class*="card"]').length > 0;
        const hasCharts = document.querySelectorAll('canvas, svg, [class*="chart"]').length > 0;
        const dataIndicators = text.match(/([\d,]+)\s+(stocks?|signals?|records?|results?|items?|rows?)/gi) || [];
        
        return {
          hasError,
          tableRows,
          hasCards,
          hasCharts,
          dataIndicators: dataIndicators.slice(0, 3),
          contentLength: text.length
        };
      });
      
      const status_str = status.hasError ? '❌ ERROR' : (status.tableRows > 0 || status.hasCards ? '✅ DATA' : '⚠️ PARTIAL');
      console.log(`${status_str} ${p.name.padEnd(25)} | Tables: ${status.tableRows} | Cards: ${status.hasCards} | Charts: ${status.hasCharts}`);
      if (status.dataIndicators.length) {
        console.log(`    └─ ${status.dataIndicators.join(' | ')}`);
      }
      
    } catch (err) {
      console.log(`❌ FAILED ${p.name.padEnd(25)} | ${err.message.substring(0, 40)}`);
    }
  }

  await browser.close();
})();
