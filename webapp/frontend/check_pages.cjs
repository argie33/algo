const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  await page.setViewportSize({ width: 1920, height: 1080 });
  
  try {
    console.log('Opening http://localhost:5173...\n');
    await page.goto('http://localhost:5173', { waitUntil: 'load', timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(2000);
    
    const screenshotsDir = '/tmp/screenshots';
    if (!fs.existsSync(screenshotsDir)) {
      fs.mkdirSync(screenshotsDir, { recursive: true });
    }

    // List of pages to check based on common navigation patterns
    const pagesToCheck = [
      { name: 'Dashboard', path: '/dashboard' },
      { name: 'Trading Signals', path: '/signals' },
      { name: 'Portfolio', path: '/portfolio' },
      { name: 'Markets Health', path: '/markets-health' },
      { name: 'Sector Analysis', path: '/sectors' },
      { name: 'Economic Data', path: '/economic' },
      { name: 'Scores', path: '/scores' },
      { name: 'Swing Candidates', path: '/swing-candidates' },
      { name: 'Trade Tracker', path: '/trades' },
      { name: 'Service Health', path: '/health' }
    ];
    
    const notEnoughDataPages = [];
    let checked = 0;
    
    for (const item of pagesToCheck) {
      try {
        console.log(`Checking: ${item.name} (${item.path})`);
        await page.goto(`http://localhost:5173${item.path}`, { waitUntil: 'domcontentloaded', timeout: 10000 }).catch(() => {});
        await page.waitForTimeout(1500);
        
        const pageText = await page.textContent('body');
        const hasNoData = pageText.includes('not enough') || 
                          pageText.includes('No data') ||
                          pageText.includes('insufficient') ||
                          pageText.includes('no data available') ||
                          pageText.includes('insufficient data');
        
        if (hasNoData) {
          notEnoughDataPages.push(item.name);
          console.log(`  ⚠️  MISSING DATA\n`);
          
          const screenshot = path.join(screenshotsDir, `${item.name.replace(/\s+/g, '_')}.png`);
          await page.screenshot({ path: screenshot, fullPage: true });
          console.log(`  📷 Saved: ${screenshot}\n`);
        } else {
          console.log(`  ✓ Has data\n`);
        }
      } catch (e) {
        console.log(`  ❌ Error: ${e.message}\n`);
      }
    }
    
    console.log('='.repeat(70));
    console.log(`PAGES WITH MISSING DATA: ${notEnoughDataPages.length}`);
    console.log('='.repeat(70));
    notEnoughDataPages.forEach(p => console.log(`  • ${p}`));
    console.log(`\nScreenshots saved to: ${screenshotsDir}`);
    
  } catch (e) {
    console.error('Fatal error:', e.message);
  }
  
  await browser.close();
})();
