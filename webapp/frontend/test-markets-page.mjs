import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

// Collect API calls
const apiCalls = [];
const apiErrors = [];
const consoleLogs = [];

page.on('response', async (response) => {
    if (response.url().includes('/api/')) {
        const status = response.status();
        const url = response.url();
        apiCalls.push({ status, url });

        if (status >= 400) {
            try {
                const body = await response.text();
                apiErrors.push({ status, url, body });
                console.log(`ERROR: ${status} ${url}`);
                console.log(`Response: ${body.substring(0, 300)}`);
            } catch (e) {
                console.log(`ERROR: ${status} ${url}`);
            }
        }
    }
});

page.on('console', (msg) => {
    consoleLogs.push(msg.text());
    if (msg.type() === 'error') {
        console.log(`CONSOLE ERROR: ${msg.text()}`);
    }
});

await page.setViewportSize({ width: 1920, height: 1080 });

try {
    console.log('Navigating to Markets Dashboard (public page)...');
    await page.goto('http://localhost:5177/app/markets', { timeout: 30000, waitUntil: 'networkidle' });

    await page.waitForTimeout(3000);

    // Take a screenshot
    await page.screenshot({ path: 'markets-dashboard.png', fullPage: true });
    console.log('Screenshot saved as markets-dashboard.png');

} catch (error) {
    console.error('Error:', error.message);
} finally {
    console.log(`\nTotal API calls: ${apiCalls.length}`);
    console.log(`Total API errors: ${apiErrors.length}`);

    if (apiErrors.length > 0) {
        console.log('API Errors:');
        apiErrors.forEach(err => {
            console.log(`  ${err.status} ${err.url}`);
        });
    }

    // Group by endpoint
    const endpointCounts = {};
    apiCalls.forEach(call => {
        const key = call.url.split('/api/')[1].split('?')[0];
        endpointCounts[key] = (endpointCounts[key] || 0) + 1;
    });

    console.log('API Endpoints called:');
    Object.entries(endpointCounts).forEach(([ep, count]) => {
        console.log(`  /api/${ep} (${count})`);
    });

    await browser.close();
}
