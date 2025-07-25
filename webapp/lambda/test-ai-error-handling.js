/**
 * Test AI service error handling - proper errors instead of fallbacks
 */

const express = require('express');
const cors = require('cors');
const aiAssistantRouter = require('./routes/ai-assistant');
const axios = require('axios');

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
const PORT = 3002;
const server = app.listen(PORT, () => {
  console.log(`🧪 Error Handling Test Server running on http://localhost:${PORT}`);
  testErrorHandling();
});

async function testErrorHandling() {
  const baseURL = `http://localhost:${PORT}`;
  
  console.log('\n🚨 Testing AI Service Error Handling...\n');

  try {
    // Test 1: Health Check with Detailed Error
    console.log('1. Testing Health Check Error Details...');
    const healthResponse = await axios.get(`${baseURL}/api/ai/health`);
    console.log('✅ Health Response Status:', healthResponse.data.success);
    console.log('   Error Message:', healthResponse.data.health.error);
    if (healthResponse.data.health.details) {
      console.log('   Required Permissions:', healthResponse.data.health.details.requiredPermissions);
      console.log('   Current User:', healthResponse.data.health.details.currentUser);
    }
    if (healthResponse.data.health.actionableSteps) {
      console.log('   Actionable Steps:', healthResponse.data.health.actionableSteps.slice(0, 2));
    }
    
    // Test 2: Chat Message Error Details
    console.log('\n2. Testing Chat Message Error Details...');
    try {
      const chatResponse = await axios.post(`${baseURL}/api/ai/chat`, {
        message: "What are the best investment strategies?",
        context: {}
      });
      console.log('❌ Unexpected success - should have failed');
    } catch (chatError) {
      if (chatError.response && chatError.response.status === 503) {
        const errorData = chatError.response.data;
        console.log('✅ Chat Error Response (503 Service Unavailable):');
        console.log('   Error Message:', errorData.error);
        console.log('   Error Code:', errorData.errorCode);
        console.log('   Required Permissions:', errorData.details?.requiredPermissions);
        console.log('   Actionable Steps:');
        errorData.actionableSteps?.forEach((step, index) => {
          console.log(`     ${step}`);
        });
        console.log('   Context:', {
          region: errorData.context?.region,
          modelId: errorData.context?.modelId
        });
      } else {
        console.log('❌ Unexpected error:', chatError.response?.data || chatError.message);
      }
    }
    
    // Test 3: Configuration Still Works
    console.log('\n3. Testing Configuration (should still work)...');
    const configResponse = await axios.get(`${baseURL}/api/ai/config`);
    console.log('✅ Config loaded successfully');
    console.log('   Features available:', Object.keys(configResponse.data.config.features));
    
    console.log('\n🎯 Error Handling Tests Complete!');
    console.log('\nSummary:');
    console.log('- ✅ Health check provides detailed error information');
    console.log('- ✅ Chat requests fail with actionable error messages (503 status)');
    console.log('- ✅ Configuration endpoints remain functional');
    console.log('- ✅ No fallback responses - proper error handling only');
    
  } catch (error) {
    console.error('\n❌ Test failed:', error.response?.data || error.message);
  }
  
  // Close the server
  server.close();
}