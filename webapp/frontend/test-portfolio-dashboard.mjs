import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

// Collect API calls
const apiCalls = [];
page.on('response', async (response) => {
    if (response.url().includes('/api/')) {
        const status = response.status();
        const url = response.url().split('/api/')[1];
        apiCalls.push({ status, endpoint: url });
        
        if (status >= 400) {
            try {
                const body = await response.text();
                console.log(\[ERROR \] /api/\\);
                console.log(\Body: \\);
            } catch (e) {
                console.log(\[ERROR \] /api/\\);
            }
        }
    }
});

await page.setViewportSize({ width: 1920, height: 1080 });

try {
    console.log('Navigating to Portfolio Dashboard...');
    // Try the portfolio dashboard page
    await page.goto('http://localhost:5177/app/portfolio', { timeout: 30000, waitUntil: 'networkidle' });
    
    await page.waitForTimeout(5000);
    
    // Take a screenshot
    await page.screenshot({ path: 'portfolio-dashboard.png', fullPage: true });
    console.log('Screenshot saved as portfolio-dashboard.png');
    
} catch (error) {
    console.error('Error:', error.message);
} finally {
    console.log(\Total API calls: \\);
    
    // Group by endpoint
    const endpointCounts = {};
    apiCalls.forEach(call => {
        const key = call.endpoint.split('?')[0];
        endpointCounts[key] = (endpointCounts[key] || 0) + 1;
    });
    
    console.log('API Endpoints called:');
    Object.entries(endpointCounts).forEach(([ep, count]) => {
        console.log(\  /api/\ (x\)\);
    });
    
    await browser.close();
}
