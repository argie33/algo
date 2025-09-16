#!/usr/bin/env node

const axios = require('axios');

const FRONTEND_URL = 'http://localhost:3002';

// Test essential pages
const ESSENTIAL_PAGES = [
  '/',
  '/market',
  '/portfolio',
  '/screener',
  '/stocks/AAPL',
  '/settings'
];

async function testPageResponse(path) {
  try {
    const response = await axios.get(`${FRONTEND_URL}${path}`, {
      timeout: 10000,
      headers: {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'User-Agent': 'Mozilla/5.0 (compatible; Frontend-Test/1.0)'
      }
    });

    const hasReactApp = response.data.includes('id="root"') ||
                       response.data.includes('React') ||
                       response.data.includes('Financial Dashboard');

    return {
      path,
      status: 'SUCCESS',
      statusCode: response.status,
      hasReactApp,
      size: response.data.length,
      title: response.data.match(/<title[^>]*>([^<]+)<\/title>/i)?.[1] || 'No title'
    };
  } catch (error) {
    return {
      path,
      status: 'ERROR',
      statusCode: error.response?.status || 'N/A',
      error: error.message
    };
  }
}

async function testFrontendPages() {
  console.log('🌐 Testing frontend page responses...\n');

  const results = [];
  let successCount = 0;

  for (const path of ESSENTIAL_PAGES) {
    console.log(`Testing: ${path}`);
    const result = await testPageResponse(path);
    results.push(result);

    if (result.status === 'SUCCESS') {
      successCount++;
      console.log(`✅ ${result.statusCode} - ${result.title} - ${result.hasReactApp ? 'React App' : 'Static'}`);
    } else {
      console.log(`❌ ${result.statusCode} - ${result.error}`);
    }

    await new Promise(resolve => setTimeout(resolve, 100));
  }

  console.log(`\n📊 SUMMARY:`);
  console.log(`Pages tested: ${ESSENTIAL_PAGES.length}`);
  console.log(`Successful: ${successCount}`);
  console.log(`Success rate: ${((successCount / ESSENTIAL_PAGES.length) * 100).toFixed(1)}%`);

  return results;
}

testFrontendPages().catch(console.error);