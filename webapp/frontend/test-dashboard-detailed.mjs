import { chromium } from 'playwright';
import fs from 'fs';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

// Collect logs and errors
const logs = [];
const errors = [];
const networkErrors = [];

// Listen for console messages
page.on('console', (msg) => {
    const entry = { type: msg.type(), text: msg.text() };
    logs.push(entry);
    if (msg.type() === 'error') {
        errors.push(entry);
        console.log('[[31mERROR[0m]', msg.text());
    }
});

// Listen for failed network requests
page.on('requestfailed', (request) => {
    networkErrors.push({
        url: request.url(),
        failure: request.failure()?.errorText
    });
});

// Set viewport
await page.setViewportSize({ width: 1920, height: 1080 });

try {
    console.log('Navigating to http://localhost:5177/app...');
    const response = await page.goto('http://localhost:5177/app', { timeout: 30000, waitUntil: 'networkidle' });
    console.log('Navigation response:', response.status());
    
    // Wait for content to load
    await page.waitForTimeout(5000);
    
    // Get the page content to see what's displayed
    const content = await page.content();
    
    // Take a screenshot
    await page.screenshot({ path: 'dashboard-detailed.png', fullPage: true });
    console.log('Screenshot saved');
    
    // Get all API request URLs from the network log
    console.log('\\n=== Network Requests ===');
    page.on('response', (response) => {
        if (response.url().includes('/api/')) {
            console.log(\\ \\);
            if (response.status() >= 400) {
                response.text().then(body => {
                    console.log('Response body:', body.substring(0, 200));
                });
            }
        }
    });
    
    // Wait for any pending requests
    await page.waitForTimeout(3000);
    
} catch (error) {
    console.error('Error:', error.message);
} finally {
    console.log('\\n=== Collected Logs ===');
    console.log('Total console messages:', logs.length);
    console.log('Total errors:', errors.length);
    console.log('Network errors:', networkErrors.length);
    
    if (networkErrors.length > 0) {
        console.log('\\n=== Network Errors ===');
        networkErrors.forEach(err => {
            console.log(\\ - \\);
        });
    }
    
    await browser.close();
}
