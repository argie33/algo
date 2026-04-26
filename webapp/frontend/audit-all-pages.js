import puppeteer from 'puppeteer';

const pageRoutes = [
  '/app/market', '/app/sectors', '/app/scores', '/app/trading-signals', '/app/financial-data',
  '/app/deep-value', '/app/etf-signals', '/app/earnings', '/app/economic', '/app/hedge',
  '/app/portfolio', '/app/portfolio-optimizer', '/app/commodity-analysis', '/app/sentiment',
  '/app/trade-history', '/app/messages', '/app/services', '/app/settings', '/api-docs'
];

const pageNames = [
  'Market Overview', 'Sector Analysis', 'Stock Scores', 'Trading Signals', 'Financial Data',
  'Deep Value', 'ETF Signals', 'Earnings Calendar', 'Economic Dashboard', 'Hedge Helper',
  'Portfolio Dashboard', 'Portfolio Optimizer', 'Commodities', 'Sentiment',
  'Trade History', 'Messages', 'Service Health', 'Settings', 'API Docs'
];

(async () => {
  const browser = await puppeteer.launch({ headless: true });
  const results = [];

  for (let i = 0; i < pageRoutes.length; i++) {
    const p = await browser.newPage();
    const route = pageRoutes[i];
    const name = pageNames[i];
    
    const errors = [];
    const networkErrors = [];
    let loaded = false;

    p.on('console', msg => {
      if (msg.type() === 'error') errors.push(msg.text());
    });

    p.on('response', response => {
      if (response.status() >= 400) {
        networkErrors.push(`${response.status()} ${response.url().split('/').slice(-1)[0]}`);
      }
    });

    try {
      await p.goto(`http://localhost:5173${route}`, { waitUntil: 'networkidle2', timeout: 15000 });
      await new Promise(r => setTimeout(r, 1000));
      loaded = true;
    } catch (e) {
      errors.push(`Load failed: ${e.message}`);
    }

    results.push({ name, loaded, errors: errors.length, networkErrors: networkErrors.length });
    await p.close();
  }

  await browser.close();

  console.log('\n📋 COMPLETE PAGE AUDIT\n');
  console.log('Page'.padEnd(30) + 'Status'.padEnd(12) + 'Errors'.padEnd(10) + 'Network');
  console.log('='.repeat(70));
  
  let allGood = true;
  results.forEach(r => {
    const status = r.loaded ? '✅ Loaded' : '❌ Failed';
    const errors = r.errors > 0 ? `${r.errors}` : '0';
    const network = r.networkErrors > 0 ? `${r.networkErrors}` : '0';
    if (!r.loaded || r.errors > 0 || r.networkErrors > 0) allGood = false;
    console.log(r.name.padEnd(30) + status.padEnd(12) + errors.padEnd(10) + network);
  });
  
  console.log('\n' + (allGood ? '✅ ALL PAGES CLEAN' : '⚠️  ISSUES FOUND'));
})();
