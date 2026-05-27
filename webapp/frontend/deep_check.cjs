const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  await page.setViewportSize({ width: 1920, height: 1080 });
  
  try {
    // Check specific pages
    const pagesToCheck = [
      '/scores',
      '/swing-candidates',
      '/economic',
      '/sectors'
    ];
    
    for (const route of pagesToCheck) {
      console.log(`\n${'='.repeat(60)}`);
      console.log(`PAGE: ${route}`);
      console.log('='.repeat(60));
      
      await page.goto(`http://localhost:5173${route}`, { waitUntil: 'networkidle', timeout: 15000 }).catch(() => {});
      await page.waitForTimeout(2000);
      
      // Get body text
      const bodyText = await page.textContent('body');
      const lower = bodyText.toLowerCase();
      
      const issues = [];
      if (lower.includes('not enough')) issues.push('not enough data');
      if (lower.includes('no data')) issues.push('no data');
      if (lower.includes('insufficient')) issues.push('insufficient');
      if (lower.includes('no symbols')) issues.push('no symbols');
      if (lower.includes('error')) issues.push('error');
      
      if (issues.length > 0) {
        console.log(`⚠️  Found: ${issues.join(', ')}`);
      } else {
        console.log('✓ Page looks good');
      }
    }
    
  } catch (e) {
    console.error('Error:', e.message);
  }
  
  await browser.close();
})();
