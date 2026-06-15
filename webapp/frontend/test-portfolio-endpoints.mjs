import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

const endpoints = {};

page.on('response', async (response) => {
    const url = response.url();
    if (url.includes('/api/algo/')) {
        const endpoint = url.split('/api/')[1];
        const status = response.status();

        try {
            const body = await response.text();
            const isJson = response.headers()['content-type']?.includes('application/json');

            endpoints[endpoint] = {
                status,
                body: isJson ? JSON.parse(body) : body.substring(0, 200),
                error: status >= 400 ? true : false
            };

            if (status >= 400) {
                console.log(`ERROR: ${status} ${endpoint}`);
            }
        } catch (e) {
            endpoints[endpoint] = { status, error: 'Failed to parse' };
        }
    }
});

await page.setViewportSize({ width: 1920, height: 1080 });

try {
    console.log('Loading dashboard...');
    await page.goto('http://localhost:5177/app/markets', { timeout: 30000, waitUntil: 'networkidle' });
    await page.waitForTimeout(3000);

    console.log('\n=== API Endpoints Status ===\n');

    const errorEndpoints = [];
    const keyEndpoints = ['algo/status', 'algo/positions', 'algo/performance', 'algo/trades', 'algo/markets', 'algo/equity-curve', 'algo/circuit-breakers'];

    for (const [endpoint, data] of Object.entries(endpoints).sort()) {
        const isKeyEndpoint = keyEndpoints.some(ke => endpoint.includes(ke));
        const marker = isKeyEndpoint ? '⭐' : '  ';
        const statusMarker = data.error ? '❌' : '✅';

        console.log(`${marker} ${statusMarker} ${data.status} - ${endpoint}`);

        if (data.error) {
            errorEndpoints.push(endpoint);
            if (data.body) {
                console.log(`   Response: ${JSON.stringify(data.body).substring(0, 150)}`);
            }
        }
    }

    if (errorEndpoints.length > 0) {
        console.log(`\n⚠️ ${errorEndpoints.length} endpoints failed:`);
        errorEndpoints.forEach(ep => console.log(`   - ${ep}`));
    } else {
        console.log('\n✅ All endpoints returned 2xx status');
    }

} catch (error) {
    console.error('Error:', error.message);
} finally {
    await browser.close();
}
