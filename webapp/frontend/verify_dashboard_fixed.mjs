import { chromium } from 'playwright';

async function verifyDashboard() {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  
  await page.setViewportSize({ width: 1920, height: 1200 });
  
  try {
    console.log('Navigating to dashboard...');
    await page.goto('http://localhost:5173', { 
      waitUntil: 'networkidle',
      timeout: 30000 
    });
    
    await page.waitForTimeout(3000);
    
    // Check for error messages
    const errors = await page.evaluate(() => {
      const errorElements = [];
      document.querySelectorAll('*').forEach(el => {
        const text = el.textContent;
        if (text && (text.includes('API Connection Issue') || 
                     text.includes('unavailable') || 
                     text.includes('Error'))) {
          errorElements.push(text.substring(0, 120).trim());
        }
      });
      return [...new Set(errorElements)];
    });
    
    if (errors.length > 0) {
      console.log('⚠️ Errors found:');
      errors.slice(0, 5).forEach(e => console.log(`  - ${e}`));
    } else {
      console.log('✅ No API connection errors');
    }
    
    // Take screenshot
    await page.screenshot({ path: './dashboard_fixed.png', fullPage: true });
    console.log('✅ Screenshot saved');
    
  } finally {
    await browser.close();
  }
}

verifyDashboard();
