#!/usr/bin/env node
/**
 * API Key Endpoints Test
 * Tests the API key management endpoints after database setup
 */

const https = require('https');

const config = {
    baseUrl: 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev',
    timeout: 10000
};

function makeRequest(options, data = null) {
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
        
        if (data) {
            req.write(JSON.stringify(data));
        }
        
        req.end();
    });
}

async function testApiKeyEndpoints() {
    console.log('🔑 Testing API Key Management Endpoints...');
    
    const tests = [
        {
            name: 'Health Check',
            endpoint: '/health',
            method: 'GET',
            expectAuth: false,
            expectStatus: 200
        },
        {
            name: 'Database Ready Check',
            endpoint: '/health/ready',
            method: 'GET',
            expectAuth: false,
            expectStatus: 200
        },
        {
            name: 'Secrets Status',
            endpoint: '/debug/secrets-status',
            method: 'GET',
            expectAuth: false,
            expectStatus: 200
        },
        {
            name: 'Settings API Keys (No Auth)',
            endpoint: '/settings/api-keys',
            method: 'GET',
            expectAuth: true,
            expectStatus: 401
        },
        {
            name: 'Portfolio Holdings (No Auth)',
            endpoint: '/portfolio/holdings',
            method: 'GET',
            expectAuth: true,
            expectStatus: 401
        },
        {
            name: 'Portfolio Root (No Auth)',
            endpoint: '/portfolio',
            method: 'GET',
            expectAuth: true,
            expectStatus: 401
        }
    ];
    
    const results = [];
    
    for (const test of tests) {
        try {
            console.log(`Testing ${test.name}...`);
            
            const url = new URL(`${config.baseUrl}${test.endpoint}`);
            const options = {
                hostname: url.hostname,
                port: 443,
                path: url.pathname + url.search,
                method: test.method,
                headers: {
                    'Content-Type': 'application/json'
                }
            };
            
            const response = await makeRequest(options);
            
            const passed = response.statusCode === test.expectStatus;
            const result = {
                test: test.name,
                endpoint: test.endpoint,
                expected: test.expectStatus,
                actual: response.statusCode,
                passed,
                data: response.data,
                authRequired: test.expectAuth
            };
            
            results.push(result);
            
            if (passed) {
                console.log(`✅ ${test.name} - ${response.statusCode} as expected`);
                if (response.data && typeof response.data === 'object') {
                    if (response.data.status) console.log(`   Status: ${response.data.status}`);
                    if (response.data.ready !== undefined) console.log(`   Ready: ${response.data.ready}`);
                    if (response.data.database?.status) console.log(`   Database: ${response.data.database.status}`);
                }
            } else {
                console.log(`❌ ${test.name} - Expected ${test.expectStatus}, got ${response.statusCode}`);
                console.log(`   Response: ${response.body.substring(0, 200)}...`);
            }
            
        } catch (error) {
            console.log(`❌ ${test.name} - Error: ${error.message}`);
            results.push({
                test: test.name,
                endpoint: test.endpoint,
                expected: test.expectStatus,
                actual: 'ERROR',
                passed: false,
                error: error.message,
                authRequired: test.expectAuth
            });
        }
    }
    
    // Summary
    const passed = results.filter(r => r.passed).length;
    const total = results.length;
    
    console.log('\n📊 API KEY ENDPOINTS TEST RESULTS');
    console.log('='.repeat(50));
    console.log(`✅ Tests passed: ${passed}/${total}`);
    console.log(`❌ Tests failed: ${total - passed}/${total}`);
    
    // Detailed results for key endpoints
    console.log('\n🔍 KEY ENDPOINT STATUS:');
    const keyEndpoints = results.filter(r => 
        r.endpoint.includes('/health') || 
        r.endpoint.includes('/settings') || 
        r.endpoint.includes('/portfolio')
    );
    
    keyEndpoints.forEach(r => {
        const status = r.passed ? '✅' : '❌';
        const auth = r.authRequired ? '🔒' : '🌐';
        console.log(`${status} ${auth} ${r.endpoint} - ${r.actual}`);
    });
    
    return passed === total;
}

// Run test
if (require.main === module) {
    testApiKeyEndpoints()
        .then(success => {
            console.log(success ? '\n🎉 All API endpoints working correctly!' : '\n⚠️  Some endpoints have issues');
            process.exit(success ? 0 : 1);
        })
        .catch(error => {
            console.error('Test execution failed:', error);
            process.exit(1);
        });
}

module.exports = { testApiKeyEndpoints };