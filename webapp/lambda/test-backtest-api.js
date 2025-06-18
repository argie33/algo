const axios = require('axios');

// Test the backtesting API endpoint
async function testBacktestAPI() {
  const baseURL = process.env.API_BASE_URL || 'http://localhost:3000/api';
  
  // Test data
  const backtestRequest = {
    strategy: `
      // Simple Buy and Hold Strategy
      const symbols = ['AAPL', 'GOOGL', 'MSFT'];
      
      // Buy equal amounts of each symbol on first opportunity
      for (const symbol of symbols) {
        if (data[symbol] && !getPosition(symbol)) {
          const price = data[symbol].close;
          const quantity = Math.floor(cash / (price * symbols.length));
          
          if (quantity > 0) {
            buy(symbol, quantity, price);
            log(\`Bought \${quantity} shares of \${symbol} at $\${price.toFixed(2)}\`);
          }
        }
      }
    `,
    config: {
      initialCapital: 100000,
      commission: 0.001,
      slippage: 0.001
    },
    symbols: ['AAPL', 'GOOGL', 'MSFT'],
    startDate: '2023-01-01',
    endDate: '2023-12-31'
  };

  try {
    console.log('Testing backtest API endpoint...');
    console.log('Request:', JSON.stringify(backtestRequest, null, 2));
    
    const response = await axios.post(`${baseURL}/backtest/run`, backtestRequest, {
      headers: {
        'Content-Type': 'application/json'
      },
      timeout: 30000 // 30 seconds timeout
    });
    
    console.log('✓ Backtest completed successfully');
    console.log('Response status:', response.status);
    console.log('Metrics:', JSON.stringify(response.data.metrics, null, 2));
    console.log('Number of trades:', response.data.trades.length);
    console.log('Final positions:', response.data.finalPositions.length);
    
  } catch (error) {
    console.error('✗ Backtest failed');
    if (error.response) {
      console.error('Status:', error.response.status);
      console.error('Error:', error.response.data);
    } else {
      console.error('Error:', error.message);
    }
  }
}

// Test other endpoints
async function testOtherEndpoints() {
  const baseURL = process.env.API_BASE_URL || 'http://localhost:3000/api';
  
  try {
    // Test symbols endpoint
    console.log('\nTesting symbols endpoint...');
    const symbolsResponse = await axios.get(`${baseURL}/backtest/symbols?search=AA&limit=10`);
    console.log('✓ Symbols endpoint working');
    console.log('Found symbols:', symbolsResponse.data.symbols.length);
    
    // Test templates endpoint
    console.log('\nTesting templates endpoint...');
    const templatesResponse = await axios.get(`${baseURL}/backtest/templates`);
    console.log('✓ Templates endpoint working');
    console.log('Available templates:', templatesResponse.data.templates.length);
    
    // Test validate endpoint
    console.log('\nTesting validate endpoint...');
    const validateResponse = await axios.post(`${baseURL}/backtest/validate`, {
      strategy: 'console.log("test");'
    });
    console.log('✓ Validate endpoint working');
    console.log('Validation result:', validateResponse.data);
    
  } catch (error) {
    console.error('✗ Endpoint test failed');
    if (error.response) {
      console.error('Status:', error.response.status);
      console.error('Error:', error.response.data);
    } else {
      console.error('Error:', error.message);
    }
  }
}

// Run tests
async function runTests() {
  console.log('='.repeat(50));
  console.log('BACKTESTING API TESTS');
  console.log('='.repeat(50));
  
  await testOtherEndpoints();
  await testBacktestAPI();
  
  console.log('\n' + '='.repeat(50));
  console.log('TESTS COMPLETED');
  console.log('='.repeat(50));
}

// Run if this file is executed directly
if (require.main === module) {
  runTests().catch(console.error);
}

module.exports = { testBacktestAPI, testOtherEndpoints, runTests };
