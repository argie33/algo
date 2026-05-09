const { chromium } = require('playwright');
const fs = require('fs');

async function checkFrontendErrors() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const errors = [];
  const logs = [];
  const warnings = [];

  // Capture all console messages
  page.on('console', msg => {
    const type = msg.type();
    const text = msg.text();

    if (type === 'error') {
      errors.push(text);
      console.log(`❌ ERROR: ${text}`);
    } else if (type === 'warning') {
      warnings.push(text);
      console.log(`⚠️  WARNING: ${text}`);
    } else if (type === 'log') {
      logs.push(text);
      console.log(`📋 LOG: ${text}`);
    }
  });

  // Capture page crashes and errors
  page.on('pageerror', error => {
    errors.push(`Page Error: ${error.message}`);
    console.log(`💥 PAGE ERROR: ${error.message}`);
  });

  // Capture network errors
  page.on('requestfailed', request => {
    errors.push(`Network Error: ${request.url()}`);
    console.log(`🔗 NETWORK FAILED: ${request.url()}`);
  });

  try {
    console.log('\n🚀 Loading http://localhost:5173...\n');
    const response = await page.goto('http://localhost:5173', { waitUntil: 'networkidle', timeout: 30000 });

    if (!response) {
      errors.push('Failed to load page - no response');
      console.log('❌ Failed to load page');
    } else {
      console.log(`✅ Page loaded with status ${response.status()}`);
    }

    // Wait a bit for any async operations
    await page.waitForTimeout(2000);

    // Get all images and their load status
    const images = await page.evaluate(() => {
      return Array.from(document.querySelectorAll('img')).map(img => ({
        src: img.src,
        complete: img.complete,
        naturalHeight: img.naturalHeight,
        naturalWidth: img.naturalWidth
      }));
    });

    if (images.length > 0) {
      console.log(`\n🖼️  Found ${images.length} images:`);
      images.forEach(img => {
        const status = img.complete && img.naturalHeight > 0 ? '✅' : '❌';
        console.log(`  ${status} ${img.src}`);
      });
    }

    // Get page title and content
    const title = await page.title();
    const headings = await page.evaluate(() => {
      return Array.from(document.querySelectorAll('h1, h2, h3')).map(h => h.textContent.trim()).slice(0, 5);
    });

    console.log(`\n📄 Page Title: ${title}`);
    console.log(`📑 First headings: ${headings.join(' | ')}`);

  } catch (error) {
    errors.push(`Navigation Error: ${error.message}`);
    console.log(`\n❌ NAVIGATION ERROR: ${error.message}`);
  }

  // Summary
  console.log('\n' + '='.repeat(60));
  console.log(`📊 SUMMARY`);
  console.log('='.repeat(60));
  console.log(`✅ Logs: ${logs.length}`);
  console.log(`⚠️  Warnings: ${warnings.length}`);
  console.log(`❌ Errors: ${errors.length}`);

  if (errors.length > 0) {
    console.log('\n❌ ERRORS FOUND:');
    errors.forEach((e, i) => console.log(`  ${i + 1}. ${e}`));
  }

  // Save detailed report
  const report = {
    timestamp: new Date().toISOString(),
    errors,
    warnings,
    logs
  };

  fs.writeFileSync('frontend-error-report.json', JSON.stringify(report, null, 2));
  console.log('\n📄 Detailed report saved to: frontend-error-report.json');

  await browser.close();

  return { errors: errors.length, warnings: warnings.length, logs: logs.length };
}

checkFrontendErrors().then(result => {
  if (result.errors > 0) {
    process.exit(1);
  }
}).catch(err => {
  console.error('Script error:', err);
  process.exit(1);
});
