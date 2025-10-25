const { chromium } = require('playwright');

async function main() {
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  try {
    const page = await browser.newPage({
      viewport: { width: 1280, height: 1024 }
    });

    await page.goto('http://localhost:5173/sentiment', { waitUntil: 'networkidle' });
    await page.waitForTimeout(2000);

    // Take screenshot
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5);
    const filename = `/tmp/sentiment-page-${timestamp}.png`;
    await page.screenshot({ path: filename, fullPage: true });
    console.log(`✅ Screenshot saved: ${filename}`);

    // Check content
    const pageContent = await page.content();
    if (pageContent.includes('AAPL') || pageContent.includes('Sentiment')) {
      console.log('✅ Page content loaded correctly');
    }

    if (pageContent.includes('Analyst') || pageContent.includes('analyst')) {
      console.log('✅ Analyst sentiment text found');
    }

    if (pageContent.includes('Social') || pageContent.includes('social')) {
      console.log('✅ Social sentiment text found');
    }

  } finally {
    await browser.close();
  }
}

main().catch(err => {
  console.error('Error:', err.message);
  process.exit(1);
});
