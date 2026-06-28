import { chromium } from 'playwright';
import fs from 'fs';

async function verifyDashboard() {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  
  await page.setViewportSize({ width: 1920, height: 1440 });
  
  try {
    console.log('Loading dashboard...');
    await page.goto('http://localhost:5173', { 
      waitUntil: 'networkidle',
      timeout: 30000 
    });
    
    await page.waitForTimeout(4000);
    
    // Count API errors
    const errors = await page.evaluate(() => {
      const errorTexts = [];
      const elements = document.querySelectorAll('*');
      elements.forEach(el => {
        const text = el.textContent;
        if (text && (
          text.includes('API Connection Issue') ||
          text.includes('unavailable') && text.length < 150 ||
          text.includes('persistent API issues')
        )) {
          errorTexts.push(text.trim().substring(0, 80));
        }
      });
      return [...new Set(errorTexts)];
    });
    
    console.log(`\n=== Dashboard Verification ===`);
    if (errors.length > 0) {
      console.log(`⚠️  Found ${errors.length} error message(s):`);
      errors.slice(0, 5).forEach(e => console.log(`  - ${e}`));
    } else {
      console.log('✅ No API connection error banners found');
    }
    
    // Take screenshot
    await page.screenshot({ path: './dashboard_final.png', fullPage: true });
    console.log('✅ Screenshot saved: dashboard_final.png');
    
  } catch (e) {
    console.error('Error:', e.message);
  } finally {
    await browser.close();
  }
}

verifyDashboard();
