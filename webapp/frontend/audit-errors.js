import puppeteer from 'puppeteer';

const pages = [
  { path: '/app/market', name: 'Market Overview' },
  { path: '/app/sectors', name: 'Sector Analysis' },
  { path: '/app/scores', name: 'Stock Scores' },
  { path: '/app/trading-signals', name: 'Trading Signals' },
  { path: '/app/financial-data', name: 'Financial Data' },
];

(async () => {
  const browser = await puppeteer.launch({ headless: true });
  console.log('\n📊 COMPREHENSIVE ERROR AUDIT\n');

  for (const page of pages) {
    const p = await browser.newPage();
    const errors = [];
    const networkErrors = [];

    p.on('console', msg => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });

    p.on('response', response => {
      if (response.status() >= 400) {
        networkErrors.push(`${response.status()} ${response.url()}`);
      }
    });

    try {
      await p.goto(`http://localhost:5173${page.path}`, { waitUntil: 'networkidle2', timeout: 20000 });
      await new Promise(r => setTimeout(r, 2000));

      if (errors.length > 0 || networkErrors.length > 0) {
        console.log(`❌ ${page.name}`);
        if (errors.length > 0) {
          console.log('   Console Errors:');
          errors.slice(0, 5).forEach(e => console.log(`     - ${e}`));
        }
        if (networkErrors.length > 0) {
          console.log('   Network Errors (4xx/5xx):');
          networkErrors.slice(0, 5).forEach(e => console.log(`     - ${e}`));
        }
      } else {
        console.log(`✅ ${page.name}`);
      }
    } catch (error) {
      console.log(`⚠️  ${page.name}: ${error.message}`);
    }

    await p.close();
  }

  await browser.close();
})();
