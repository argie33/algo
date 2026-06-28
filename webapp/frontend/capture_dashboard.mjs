import { chromium } from 'playwright';
import fs from 'fs';

async function captureDashboard() {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  
  await page.setViewportSize({ width: 1920, height: 1200 });
  
  try {
    console.log('Navigating to dashboard...');
    await page.goto('http://localhost:5174', { 
      waitUntil: 'networkidle',
      timeout: 30000 
    });
    
    await page.waitForTimeout(3000);
    
    // Get all panel content to identify issues
    const pageContent = await page.evaluate(() => {
      const texts = [];
      document.querySelectorAll('*').forEach(el => {
        const text = el.textContent;
        if (text && (text.includes('unavailable') || text.includes('Unavailable') || 
                     text.includes('Error') || text.includes('error') ||
                     text.includes('Failed'))) {
          texts.push(text.substring(0, 150).trim());
        }
      });
      return texts;
    });
    
    console.log('Page content check:');
    if (pageContent.length > 0) {
      console.log('Found error messages:');
      pageContent.forEach(t => console.log(`  - ${t}`));
    } else {
      console.log('No error messages found');
    }
    
    // Take full page screenshot
    const screenshotPath = './dashboard_current.png';
    await page.screenshot({ path: screenshotPath, fullPage: true });
    console.log(`Screenshot saved: ${screenshotPath}`);
    
  } catch (err) {
    console.error('Error:', err.message);
  } finally {
    await browser.close();
  }
}

captureDashboard();
