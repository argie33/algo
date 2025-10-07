#!/usr/bin/env node
/**
 * N/A Value Detector - Find all N/A, null, undefined issues in API responses
 * Tests actual API endpoints and database to identify data quality issues
 */

const axios = require('axios');

const API_BASE = 'http://localhost:5001/api';
const ISSUES = [];

async function testEndpoint(name, url) {
  try {
    console.log(`\nTesting ${name}...`);
    const response = await axios.get(url, { timeout: 5000 });

    // Check for N/A values in response
    const stringified = JSON.stringify(response.data);
    const naCount = (stringified.match(/"N\/A"|null|undefined/g) || []).length;

    if (naCount > 0) {
      ISSUES.push({
        endpoint: name,
        url,
        naCount,
        sample: findNAFields(response.data).slice(0, 5)
      });
      console.log(`  ⚠️  Found ${naCount} N/A/null values`);
    } else {
      console.log(`  ✅ No N/A values`);
    }

    return response.data;
  } catch (error) {
    console.log(`  ❌ Error: ${error.message}`);
    ISSUES.push({
      endpoint: name,
      url,
      error: error.message
    });
    return null;
  }
}

function findNAFields(obj, path = '') {
  const fields = [];

  if (Array.isArray(obj)) {
    obj.forEach((item, idx) => {
      fields.push(...findNAFields(item, `${path}[${idx}]`));
    });
  } else if (obj && typeof obj === 'object') {
    Object.keys(obj).forEach(key => {
      const value = obj[key];
      const newPath = path ? `${path}.${key}` : key;

      if (value === null || value === undefined || value === 'N/A' || value === 'not_found') {
        fields.push(newPath);
      } else if (typeof value === 'object') {
        fields.push(...findNAFields(value, newPath));
      }
    });
  }

  return fields;
}

async function main() {
  console.log('🔍 N/A Value Detection Test Suite\n');
  console.log('='.repeat(60));

  // Test health endpoint
  const health = await testEndpoint('Health', `${API_BASE}/health`);

  // Test stocks endpoint
  await testEndpoint('Stocks (limit 5)', `${API_BASE}/stocks?limit=5`);

  // Test metrics endpoint - using GOOGL which has both company profile AND price data
  await testEndpoint('Metrics (GOOGL)', `${API_BASE}/metrics/GOOGL`);

  // Test signals endpoint
  await testEndpoint('Signals (GOOGL)', `${API_BASE}/signals?symbol=GOOGL&limit=5`);

  // Test news endpoint
  await testEndpoint('News (GOOGL)', `${API_BASE}/news/GOOGL?limit=5`);

  // Summary
  console.log('\n' + '='.repeat(60));
  console.log('\n📊 SUMMARY\n');

  if (ISSUES.length === 0) {
    console.log('✅ No issues found!');
  } else {
    console.log(`❌ Found ${ISSUES.length} endpoints with issues:\n`);

    ISSUES.forEach((issue, idx) => {
      console.log(`${idx + 1}. ${issue.endpoint}`);
      console.log(`   URL: ${issue.url}`);

      if (issue.error) {
        console.log(`   Error: ${issue.error}`);
      } else {
        console.log(`   N/A Count: ${issue.naCount}`);
        if (issue.sample && issue.sample.length > 0) {
          console.log(`   Sample Fields: ${issue.sample.join(', ')}`);
        }
      }
      console.log('');
    });
  }

  // Exit with error code if issues found
  process.exit(ISSUES.length > 0 ? 1 : 0);
}

main().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
