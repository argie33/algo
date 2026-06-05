const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  try {
    console.log('Loading /app/markets...\n');
    await page.goto('http://localhost:5182/app/markets', { waitUntil: 'networkidle', timeout: 20000 });
    await page.waitForTimeout(2000);

    // Get all text content
    const text = await page.innerText('body');
    
    // Look for error-related strings
    const errorLines = text.split('\n').filter(line => 
      line.toLowerCase().includes('error') || 
      line.toLowerCase().includes('failed') ||
      line.toLowerCase().includes('undefined') ||
      line.toLowerCase().includes('null') ||
      line.toLowerCase().includes('cannot') ||
      line.toLowerCase().includes('invalid') ||
      line.toLowerCase().includes('warning')
    );

    console.log('=== ERROR/WARNING CONTENT ON PAGE ===');
    if (errorLines.length === 0) {
      console.log('No error text found on page');
    } else {
      errorLines.slice(0, 30).forEach((line, i) => {
        if (line.trim()) console.log(`${i + 1}. ${line.trim()}`);
      });
      if (errorLines.length > 30) console.log(`\n... and ${errorLines.length - 30} more lines with error keywords`);
    }

  } catch (e) {
    console.error('Error:', e.message);
  }

  await browser.close();
})();
