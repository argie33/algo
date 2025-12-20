const https = require('https');

const AWS_API_BASE = 'https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev';

async function testAPI(endpoint, description) {
  return new Promise((resolve) => {
    console.log(`\n🔍 Testing ${description}:`);
    console.log(`   ${AWS_API_BASE}${endpoint}`);

    https.get(`${AWS_API_BASE}${endpoint}`, (res) => {
      let data = '';

      res.on('data', (chunk) => {
        data += chunk;
      });

      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          console.log(`   Status: ${res.statusCode}`);

          if (res.statusCode === 200) {
            console.log(`   ✅ Success!`);
            if (parsed.data) {
              console.log(`   📊 Data count: ${Array.isArray(parsed.data) ? parsed.data.length : 'N/A'}`);
              if (Array.isArray(parsed.data) && parsed.data.length > 0) {
                console.log(`   📄 Sample: ${JSON.stringify(parsed.data[0]).substring(0, 100)}...`);
              }
            }
            if (parsed.pagination) {
              console.log(`   📈 Total records: ${parsed.pagination.total || 0}`);
            }
            if (parsed.count !== undefined) {
              console.log(`   📊 Count: ${parsed.count}`);
            }
          } else {
            console.log(`   ❌ Error: ${parsed.error || 'Unknown error'}`);
            console.log(`   💬 Message: ${parsed.message || 'No message'}`);
          }
        } catch (e) {
          console.log(`   ❌ Parse error: ${e.message}`);
          console.log(`   📄 Raw response: ${data.substring(0, 200)}...`);
        }
        resolve();
      });
    }).on('error', (err) => {
      console.log(`   ❌ Request error: ${err.message}`);
      resolve();
    });
  });
}

async function testEconomicEndpoints() {
  console.log('🚀 Testing Economic Data API Endpoints on AWS\n');

  // Test main endpoints
  await testAPI('/api/economic', 'Main economic data endpoint');
  await testAPI('/api/economic/data', 'Economic data for validation page');
  await testAPI('/api/economic/indicators', 'Economic indicators');
  await testAPI('/api/economic/calendar', 'Economic calendar');
  await testAPI('/api/economic/series/GDP', 'GDP series data');
  await testAPI('/api/economic/forecast?series=GDP', 'GDP forecast');
  await testAPI('/api/economic/correlations?series=GDP', 'GDP correlations');
  await testAPI('/api/economic/compare?series=GDP,CPI', 'GDP vs CPI comparison');

  console.log('\n✅ Economic API endpoint testing completed');
}

testEconomicEndpoints();