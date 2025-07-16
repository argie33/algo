#!/usr/bin/env node
/**
 * Portfolio Authentication Test
 * Tests that portfolio endpoints properly require authentication
 */

const https = require('https');

const config = {
    baseUrl: 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev',
    timeout: 10000
};

function makeRequest(options) {
    return new Promise((resolve, reject) => {
        const req = https.request(options, (res) => {
            let body = '';
            res.on('data', (chunk) => body += chunk);
            res.on('end', () => {
                try {
                    resolve({
                        statusCode: res.statusCode,
                        headers: res.headers,
                        body: body,
                        data: body ? JSON.parse(body) : null
                    });
                } catch (error) {
                    resolve({
                        statusCode: res.statusCode,
                        headers: res.headers,
                        body: body,
                        data: null,
                        parseError: error.message
                    });
                }
            });
        });
        
        req.on('error', reject);
        req.setTimeout(config.timeout, () => {
            req.destroy();
            reject(new Error('Request timeout'));
        });
        
        req.end();
    });
}

async function testPortfolioAuth() {
    console.log('🔐 Testing Portfolio Authentication Requirements...');
    
    const endpoints = [
        '/portfolio',
        '/portfolio/holdings', 
        '/portfolio/performance',
        '/portfolio/analytics'
    ];
    
    const results = [];
    
    for (const endpoint of endpoints) {
        try {
            const url = new URL(`${config.baseUrl}${endpoint}`);
            const options = {
                hostname: url.hostname,
                port: 443,
                path: url.pathname,
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                }
            };
            
            console.log(`Testing ${endpoint}...`);
            const response = await makeRequest(options);
            
            const passed = response.statusCode === 401;
            const result = {
                endpoint,
                statusCode: response.statusCode,
                passed,
                error: response.data?.error || response.data?.message,
                requiresAuth: passed
            };
            
            results.push(result);
            
            if (passed) {
                console.log(`✅ ${endpoint} - Properly requires authentication (401)`);
            } else {
                console.log(`❌ ${endpoint} - Security issue! Returns ${response.statusCode} without auth`);
                console.log(`   Response: ${response.body.substring(0, 200)}...`);
            }
            
        } catch (error) {
            console.log(`❌ ${endpoint} - Test error: ${error.message}`);
            results.push({
                endpoint,
                statusCode: 'ERROR',
                passed: false,
                error: error.message,
                requiresAuth: false
            });
        }
    }
    
    // Summary
    const passed = results.filter(r => r.passed).length;
    const total = results.length;
    
    console.log('\n📊 PORTFOLIO AUTHENTICATION TEST RESULTS');
    console.log('='.repeat(50));
    console.log(`✅ Secure endpoints: ${passed}/${total}`);
    console.log(`❌ Vulnerable endpoints: ${total - passed}/${total}`);
    
    if (passed === total) {
        console.log('🎉 All portfolio endpoints properly require authentication!');
        return true;
    } else {
        console.log('⚠️  SECURITY ISSUES FOUND - Some endpoints are accessible without authentication');
        
        console.log('\n🚨 VULNERABLE ENDPOINTS:');
        results.filter(r => !r.passed).forEach(r => {
            console.log(`   ${r.endpoint} - Returns ${r.statusCode}`);
        });
        return false;
    }
}

// Run test
if (require.main === module) {
    testPortfolioAuth()
        .then(success => {
            process.exit(success ? 0 : 1);
        })
        .catch(error => {
            console.error('Test execution failed:', error);
            process.exit(1);
        });
}

module.exports = { testPortfolioAuth };