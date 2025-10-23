const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  page.setViewportSize({ width: 1400, height: 900 });

  // Navigate to sectors page
  await page.goto('http://localhost:5173/sectors', { waitUntil: 'networkidle' });

  // Wait for data to load
  await page.waitForTimeout(3000);

  // Scroll to Industry Rankings section
  await page.evaluate(() => {
    const industryHeading = Array.from(document.querySelectorAll('h6'))
      .find(h => h.textContent.includes('Industry Rankings'));
    if (industryHeading) {
      industryHeading.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });

  await page.waitForTimeout(1000);

  // Take screenshot of industry rankings
  await page.screenshot({ path: '/tmp/industry_rankings.png', fullPage: false });

  console.log('✅ Industry Rankings screenshot saved to /tmp/industry_rankings.png');

  await browser.close();
})();
