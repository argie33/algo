import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

console.log('\n🔍 Testing AWS Production (CloudFront)...\n');

const failedRequests = [];
page.on('response', response => {
  if (response.status() >= 400) {
    failedRequests.push({
      status: response.status(),
      url: response.url(),
    });
  }
});

try {
  await page.goto('https://d5j1h4wzrkvw7.cloudfront.net', { waitUntil: 'networkidle', timeout: 15000 });
  
  // Check config
  const config = await page.evaluate(() => window.__CONFIG__);
  console.log('✅ Landing page loaded');
  console.log('API_URL:', config.API_URL);
  console.log('ENVIRONMENT:', config.ENVIRONMENT);
  
  // Navigate to each page briefly
  const pages = ['dashboard', 'signals', 'trades', 'portfolio'];
  for (const p of pages) {
    await page.goto(`https://d5j1h4wzrkvw7.cloudfront.net/${p}`, { waitUntil: 'domcontentloaded', timeout: 10000 });
    await page.waitForTimeout(500);
  }
  
  console.log('\n✅ All pages tested on AWS');
  console.log(`Failed requests (4xx/5xx): ${failedRequests.length}`);
  if (failedRequests.length > 0) {
    failedRequests.slice(0,3).forEach(r => console.log(`  ${r.status}: ${r.url.substring(0, 80)}`));
  }
} catch (e) {
  console.log('❌ Error:', e.message);
}

await browser.close();
