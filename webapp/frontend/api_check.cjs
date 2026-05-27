const axios = require('axios');

const endpoints = [
  '/api/scores',
  '/api/signals',
  '/api/portfolio',
  '/api/market-health',
  '/api/sectors',
  '/api/economic-data',
  '/api/swing-candidates',
  '/api/data-coverage'
];

(async () => {
  console.log('Checking API Endpoints...\n');
  
  for (const endpoint of endpoints) {
    try {
      const response = await axios.get(`http://localhost:5000${endpoint}`, { timeout: 5000 });
      const data = response.data;
      
      const itemCount = Array.isArray(data) ? data.length : 
                        data.data ? (Array.isArray(data.data) ? data.data.length : Object.keys(data.data || {}).length) : 0;
      
      console.log(`✓ ${endpoint}`);
      console.log(`  Status: ${response.status}`);
      console.log(`  Items: ${itemCount}`);
      
      if (data.error) {
        console.log(`  ⚠️  Error: ${data.error}`);
      }
    } catch (e) {
      console.log(`❌ ${endpoint}`);
      console.log(`  Error: ${e.message}`);
    }
    console.log('');
  }
})();
