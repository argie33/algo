
const axios = require('axios');

async function debugApiResponse() {
  try {
    console.log('🔍 Debugging Balance Sheet API Response Structure\n');

    const response = await axios.get('http://localhost:3001/api/financials/AAPL/balance-sheet');
    const data = response.data;

    console.log('📊 API Response Structure:');
    console.log('- Success:', data.success);
    console.log('- Data type:', Array.isArray(data.data) ? 'Array' : typeof data.data);
    console.log('- Data length:', data.data?.length || 0);
    console.log('- Metadata:', JSON.stringify(data.metadata, null, 2));

    if (data.data && data.data.length > 0) {
      const firstItem = data.data[0];
      console.log('\n📋 First Item Structure:');
      console.log('- Keys:', Object.keys(firstItem));
      console.log('- Has item_name?', 'item_name' in firstItem);
      console.log('- Date value:', firstItem.date);
      console.log('- Date type:', typeof firstItem.date);

      console.log('\n🔍 Sample item:');
      console.log(JSON.stringify(firstItem, null, 2));
    }
  } catch (error) {
    console.error('❌ Error:', error.message);
  }
}

debugApiResponse();