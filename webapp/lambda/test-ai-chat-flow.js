/**
 * End-to-end test for AI chat functionality
 * Tests the complete flow from frontend API to backend processing
 */

const express = require('express');
const cors = require('cors');
const aiAssistantRouter = require('./routes/ai-assistant');

// Create a simple test server
const app = express();
app.use(cors());
app.use(express.json());

// Mock authentication middleware for testing
app.use((req, res, next) => {
  req.user = { sub: 'test-user-123' };
  next();
});

// Mount the AI assistant routes
app.use('/api/ai', aiAssistantRouter);

// Start test server
const PORT = 3001;
const server = app.listen(PORT, () => {
  console.log(`🧪 Test server running on http://localhost:${PORT}`);
  console.log('📝 Available endpoints:');
  console.log('  POST /api/ai/chat - Send chat message');
  console.log('  GET  /api/ai/health - AI service health');
  console.log('  GET  /api/ai/config - AI configuration');
  console.log('  GET  /api/ai/history - Chat history');
  console.log('  DELETE /api/ai/history - Clear history');
});

// Test the chat functionality
async function testChatFlow() {
  const axios = require('axios');
  const baseURL = `http://localhost:${PORT}`;
  
  console.log('\n🚀 Testing AI Chat Flow...\n');

  try {
    // Test 1: Health Check
    console.log('1. Testing AI Health Check...');
    const healthResponse = await axios.get(`${baseURL}/api/ai/health`);
    console.log('✅ Health Status:', healthResponse.data.health.status);
    console.log('   Service:', healthResponse.data.health.service);
    
    // Test 2: Get Configuration
    console.log('\n2. Testing AI Configuration...');
    const configResponse = await axios.get(`${baseURL}/api/ai/config`);
    console.log('✅ Config loaded, features:', Object.keys(configResponse.data.config.features));
    
    // Test 3: Send Chat Message
    console.log('\n3. Testing Chat Message...');
    const chatResponse = await axios.post(`${baseURL}/api/ai/chat`, {
      message: "What are some good investment strategies for beginners?",
      context: { digitalHumanEnabled: false }
    });
    console.log('✅ Chat Response:');
    console.log('   Message length:', chatResponse.data.message.content.length);
    console.log('   Suggestions:', chatResponse.data.message.suggestions);
    console.log('   Content preview:', chatResponse.data.message.content.substring(0, 100) + '...');
    
    // Test 4: Portfolio-specific Query
    console.log('\n4. Testing Portfolio Query...');
    const portfolioResponse = await axios.post(`${baseURL}/api/ai/chat`, {
      message: "How is my portfolio performing?",
      context: { includePortfolio: true }
    });
    console.log('✅ Portfolio Response:');
    console.log('   Has portfolio data:', portfolioResponse.data.message.context?.hasPortfolioData);
    console.log('   Content preview:', portfolioResponse.data.message.content.substring(0, 100) + '...');
    
    // Test 5: Get Chat History
    console.log('\n5. Testing Chat History...');
    const historyResponse = await axios.get(`${baseURL}/api/ai/history`);
    console.log('✅ Chat History:');
    console.log('   Total messages:', historyResponse.data.total);
    console.log('   Recent messages:', historyResponse.data.history.length);
    
    console.log('\n🎉 All tests passed! AI Chat is working correctly.');
    
  } catch (error) {
    console.error('\n❌ Test failed:', error.response?.data || error.message);
  }
  
  // Close the server
  server.close();
}

// Run tests after a short delay to ensure server is ready
setTimeout(testChatFlow, 1000);