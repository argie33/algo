/**
 * Simple test script for AI service functionality
 * Tests both AWS Bedrock integration and fallback mechanisms
 */

const bedrockAIService = require('./utils/bedrockAIService');

async function testAIService() {
  console.log('🧪 Testing AI Service...\n');

  // Test 1: Health Check
  console.log('1. Testing Health Check...');
  try {
    const health = await bedrockAIService.healthCheck();
    console.log('✅ Health Check Result:', JSON.stringify(health, null, 2));
  } catch (error) {
    console.log('❌ Health Check Failed:', error.message);
  }

  // Test 2: Basic AI Response
  console.log('\n2. Testing Basic AI Response...');
  try {
    const response = await bedrockAIService.generateResponse(
      "What are some good investment strategies for beginners?",
      {
        userId: 'test-user',
        portfolioContext: null
      }
    );
    console.log('✅ AI Response Generated:');
    console.log('Content:', response.content.substring(0, 200) + '...');
    console.log('Suggestions:', response.suggestions);
    console.log('Context:', response.context);
  } catch (error) {
    console.log('❌ AI Response Failed:', error.message);
  }

  // Test 3: Portfolio-aware Response
  console.log('\n3. Testing Portfolio-aware Response...');
  try {
    const portfolioContext = {
      totalValue: 50000,
      totalGainLoss: 2500,
      gainLossPercent: 5.0,
      holdings: [
        { symbol: 'AAPL', market_value: '15000' },
        { symbol: 'MSFT', market_value: '12000' },
        { symbol: 'GOOGL', market_value: '10000' }
      ]
    };

    const response = await bedrockAIService.generateResponse(
      "How is my portfolio performing?",
      {
        userId: 'test-user',
        portfolioContext: portfolioContext
      }
    );
    console.log('✅ Portfolio Response Generated:');
    console.log('Content:', response.content.substring(0, 200) + '...');
    console.log('Has Portfolio Data:', response.context.hasPortfolioData);
  } catch (error) {
    console.log('❌ Portfolio Response Failed:', error.message);
  }

  // Test 4: Usage Statistics
  console.log('\n4. Testing Usage Statistics...');
  try {
    const stats = bedrockAIService.getUsageStats();
    console.log('✅ Usage Statistics:', JSON.stringify(stats, null, 2));
  } catch (error) {
    console.log('❌ Usage Statistics Failed:', error.message);
  }

  console.log('\n🏁 AI Service Testing Complete!');
}

// Run the test if this file is executed directly
if (require.main === module) {
  testAIService().catch(console.error);
}

module.exports = { testAIService };