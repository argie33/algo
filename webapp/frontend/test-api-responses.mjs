import { chromium } from 'playwright';
import fs from 'fs';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

const responses = {};

page.on('response', async (response) => {
    if (response.url().includes('/api/algo/')) {
        const status = response.status();
        const url = new URL(response.url());
        const endpoint = url.pathname.replace('/api/', '');

        try {
            const body = await response.text();
            responses[endpoint] = {
                status,
                body: body.substring(0, 1000)
            };

            if (status >= 400) {
                console.log(`ERROR: ${status} ${endpoint}`);
                console.log(`Body: ${body.substring(0, 500)}`);
            }
        } catch (e) {
            responses[endpoint] = { status, error: e.message };
        }
    }
});

await page.setViewportSize({ width: 1920, height: 1080 });

try {
    console.log('Navigating to Markets Dashboard...');
    await page.goto('http://localhost:5177/app/markets', { timeout: 30000, waitUntil: 'networkidle' });
    await page.waitForTimeout(3000);
} catch (error) {
    console.error('Error:', error.message);
} finally {
    console.log('\n=== API Responses ===\n');

    for (const [endpoint, data] of Object.entries(responses)) {
        console.log(`\nEndpoint: ${endpoint}`);
        console.log(`Status: ${data.status}`);
        if (data.body) {
            try {
                const json = JSON.parse(data.body);
                console.log('Response (parsed):');
                console.log(JSON.stringify(json, null, 2).substring(0, 500));
            } catch (e) {
                console.log(`Response (raw): ${data.body.substring(0, 300)}`);
            }
        } else if (data.error) {
            console.log(`Error: ${data.error}`);
        }
    }

    await browser.close();
}
