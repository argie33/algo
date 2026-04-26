import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  
  const partialPages = [
    { name: 'Market Overview', path: '/app/market' },
    { name: 'Sector Analysis', path: '/app/sectors' },
    { name: 'Earnings Calendar', path: '/app/earnings' }
  ];

  for (const p of partialPages) {
    console.log(`\n=== ${p.name} ===`);
    
    await page.goto(`http://localhost:5174${p.path}`, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1500);
    
    const details = await page.evaluate(() => {
      const text = document.body.innerText;
      const allText = text.toLowerCase();
      
      // Look for key data indicators
      const hasNumbers = /\$|%|\d+\.\d+|\d,\d+/.test(text);
      const hasSymbols = /[A-Z]{1,5}\s+\d+/.test(text);
      const headings = Array.from(document.querySelectorAll('h2, h3')).map(h => h.textContent).slice(0, 3);
      const errorText = Array.from(document.querySelectorAll('*')).find(el => 
        el.textContent.toLowerCase().includes('error') ||
        el.textContent.toLowerCase().includes('no data')
      )?.textContent.substring(0, 50);
      
      return {
        hasNumbers,
        hasSymbols,
        hasError: !!errorText,
        errorText,
        headings,
        contentLength: text.length,
        sampleText: text.substring(200, 400)
      };
    });
    
    console.log(`  Has numbers/values: ${details.hasNumbers}`);
    console.log(`  Has symbols: ${details.hasSymbols}`);
    console.log(`  Has error: ${details.hasError}`);
    if (details.errorText) console.log(`  Error: ${details.errorText}`);
    if (details.headings.length) console.log(`  Headings: ${details.headings.join(' | ')}`);
    console.log(`  Content length: ${details.contentLength}`);
  }

  await browser.close();
})();
