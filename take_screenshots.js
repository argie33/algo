const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const screenshots = [];
let browser;

async function main() {
  try {
    browser = await chromium.launch({
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    });

    const context = await browser.createContext({
      viewport: { width: 1280, height: 1024 }
    });

    const page = await context.newPage();

    // Set extended timeout
    page.setDefaultTimeout(30000);
    page.setDefaultNavigationTimeout(30000);

    console.log('Taking screenshots of Sentiment page...');

    // Navigate to sentiment page
    await page.goto('http://localhost:5173/sentiment', { waitUntil: 'networkidle' });

    // Wait for page to fully load
    await page.waitForTimeout(3000);

    // Take full page screenshot
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5);
    const filename1 = `/tmp/sentiment-page-${timestamp}.png`;
    await page.screenshot({ path: filename1, fullPage: true });
    console.log(`✅ Screenshot saved: ${filename1}`);
    screenshots.push(filename1);

    // Scroll to see analyst sentiment section
    await page.evaluate(() => {
      document.querySelector('[data-testid="analyst-sentiment"]')?.scrollIntoView();
    });
    await page.waitForTimeout(1000);

    const filename2 = `/tmp/sentiment-analyst-section-${timestamp}.png`;
    await page.screenshot({ path: filename2 });
    console.log(`✅ Screenshot saved: ${filename2}`);
    screenshots.push(filename2);

    // Scroll to social sentiment section
    await page.evaluate(() => {
      document.querySelector('[data-testid="social-sentiment"]')?.scrollIntoView();
    });
    await page.waitForTimeout(1000);

    const filename3 = `/tmp/sentiment-social-section-${timestamp}.png`;
    await page.screenshot({ path: filename3 });
    console.log(`✅ Screenshot saved: ${filename3}`);
    screenshots.push(filename3);

    // Check for errors in console
    page.on('console', msg => {
      if (msg.type() === 'error') {
        console.log(`❌ Console error: ${msg.text()}`);
      }
    });

    // Check page content
    const pageContent = await page.content();
    if (pageContent.includes('Analyst Sentiment') && !pageContent.includes('Failed to fetch')) {
      console.log('✅ Analyst Sentiment section loaded successfully');
    } else {
      console.log('⚠️  Could not verify analyst sentiment');
    }

    if (pageContent.includes('Social Sentiment') || pageContent.includes('Community Sentiment')) {
      console.log('✅ Social Sentiment section found');
    } else {
      console.log('⚠️  Could not find social sentiment section');
    }

    await context.close();

    console.log('\n✅ All screenshots completed successfully!');
    console.log('\nScreenshot files:');
    screenshots.forEach(f => console.log(`  - ${f}`));

  } catch (error) {
    console.error('❌ Error:', error.message);
    process.exit(1);
  } finally {
    if (browser) {
      await browser.close();
    }
  }
}

main();
