import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

// Set viewport for a better view
await page.setViewportSize({ width: 1920, height: 1080 });

// Navigate to the dashboard
try {
    console.log('Navigating to http://localhost:5177/app...');
    await page.goto('http://localhost:5177/app', { timeout: 30000, waitUntil: 'networkidle' });
    
    // Wait a bit for content to load
    await page.waitForTimeout(3000);
    
    // Take a screenshot
    await page.screenshot({ path: 'dashboard-screenshot.png', fullPage: true });
    console.log('Screenshot saved as dashboard-screenshot.png');
    
    // Check for any console errors
    page.on('console', (msg) => {
        if (msg.type() === 'error') {
            console.log('BROWSER ERROR:', msg.text());
        }
    });
    
    // Wait a bit more to catch any errors
    await page.waitForTimeout(2000);
} catch (error) {
    console.error('Error:', error.message);
} finally {
    await browser.close();
}
