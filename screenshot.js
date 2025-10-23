const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  // Navigate to sectors page
  await page.goto('http://localhost:5173/sectors', { waitUntil: 'networkidle' });

  // Wait for data to load
  await page.waitForTimeout(2000);

  // Take screenshot
  await page.screenshot({ path: '/tmp/sectors_page.png', fullPage: true });

  console.log('Screenshot saved to /tmp/sectors_page.png');

  // Get some debug info
  const sectorNames = await page.locator('h3').allTextContents();
  console.log('Visible Sector Headers:', sectorNames.slice(0, 10));

  const industryAccordions = await page.locator('AccordionSummary').count();
  console.log('Number of accordion items:', industryAccordions);

  await browser.close();
})();
