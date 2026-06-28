import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext();
const page = await context.newPage();

// Collect network activity
const apiErrors = [];
const apiResponses = [];

// Listen for all responses
page.on('response', async (response) => {
    if (response.url().includes('/api/')) {
        const status = response.status();
        const url = response.url();
        apiResponses.push({ status, url });

        if (status >= 400) {
            try {
                const body = await response.text();
                apiErrors.push({ status, url, body: body.substring(0, 300) });
                console.log(`ERROR: ${status} ${url}`);
                console.log(`Response: ${body.substring(0, 300)}`);
            } catch (e) {
                console.log(`ERROR: ${status} ${url} (could not read body)`);
            }
        } else {
            console.log(`OK: ${status} ${url}`);
        }
    }
});

// Set viewport
await page.setViewportSize({ width: 1920, height: 1080 });

try {
    console.log('Navigating to dashboard...');
    await page.goto('http://localhost:5177/app', { timeout: 30000, waitUntil: 'networkidle' });

    // Wait for content to load
    await page.waitForTimeout(5000);

    // Take a screenshot
    await page.screenshot({ path: 'dashboard-api-errors.png', fullPage: true });
    console.log('Screenshot saved as dashboard-api-errors.png');

} catch (error) {
    console.error('Navigation error:', error.message);
} finally {
    console.log('\n=== Summary ===');
    console.log('Total API responses:', apiResponses.length);
    console.log('Total API errors:', apiErrors.length);
    console.log('Error breakdown:');
    apiErrors.forEach(err => {
        console.log(`  ${err.status} ${err.url.substring(0, 80)}`);
    });

    await browser.close();
}
