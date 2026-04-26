import puppeteer from 'puppeteer';

const checks = [
  { path: '/app/market', name: 'Market', checkFor: ['Advancing', 'Declining', 'Volatility', 'Bullish'] },
  { path: '/app/sectors', name: 'Sectors', checkFor: ['Healthcare', 'Technology', 'Financial', 'rank'] },
  { path: '/app/scores', name: 'Scores', checkFor: ['MGRT', 'MCTA', 'Composite', '$'] },
  { path: '/app/trading-signals', name: 'Signals', checkFor: ['Buy', 'Sell', '%', 'Signal'] },
  { path: '/app/financial-data', name: 'Financial', checkFor: ['Balance Sheet', 'AAPL', '$', 'Assets'] },
];

(async () => {
  const browser = await puppeteer.launch({ headless: true });
  console.log('\n📈 DATA DISPLAY CHECK\n');

  for (const check of checks) {
    const p = await browser.newPage();
    try {
      await p.goto(`http://localhost:5173${check.path}`, { waitUntil: 'networkidle2', timeout: 20000 });
      await new Promise(r => setTimeout(r, 2000));
      
      const text = await p.evaluate(() => document.body.innerText);
      const found = check.checkFor.filter(keyword => text.includes(keyword));
      
      if (found.length === check.checkFor.length) {
        console.log(`✅ ${check.name}: ALL DATA SHOWING`);
      } else {
        console.log(`⚠️  ${check.name}: Missing ${check.checkFor.filter(k => !found.includes(k)).join(', ')}`);
      }
    } catch (error) {
      console.log(`❌ ${check.name}: ${error.message}`);
    }
    await p.close();
  }

  await browser.close();
})();
