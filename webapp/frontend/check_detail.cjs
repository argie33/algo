const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1920, height: 1080 });

  for (const url of ['/swing-candidates', '/markets-health']) {
    console.log(`\nPage: ${url}`);
    await page.goto(`http://localhost:5173${url}`, { waitUntil: 'domcontentloaded', timeout: 10000 }).catch(() => {});
    await page.waitForTimeout(2000);

    const text = await page.textContent('body');
    
    // Check for common data patterns
    const checks = [
      ['Data available', text.length > 5000],
      ['Has numbers', /\d{3,}/.test(text)],
      ['Has charts/tables', /chart|table|row|cell|grid/i.test(text)],
      ['No "not found" errors', !text.toLowerCase().includes('not found')],
      ['No "loading" message', !text.toLowerCase().includes('loading...')],
    ];

    checks.forEach(([label, result]) => {
      console.log(`  ${result ? '[+]' : '[-]'} ${label}`);
    });

    // Show first 300 chars of body text
    console.log(`  Preview: ${text.substring(0, 150)}...`);
  }

  await browser.close();
})();
