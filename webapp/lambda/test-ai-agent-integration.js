/**
 * AI Agent Integration Test
 * 
 * Tests the complete AI agent functionality including:
 * - Bedrock integration
 * - Database persistence
 * - Real-time market context
 * - Error handling
 * - Response streaming capabilities
 */

const express = require('express');
const request = require('supertest');

// Mock environment for testing
process.env.AWS_REGION = 'us-east-1';
process.env.NODE_ENV = 'test';

// Import components to test
const aiRouter = require('./routes/ai-assistant');
const bedrockAIService = require('./utils/bedrockAIService');
const conversationStore = require('./utils/conversationStore');
const aiErrorHandler = require('./utils/aiErrorHandler');
const aiStreamingService = require('./utils/aiStreamingService');

// Create test app
const app = express();
app.use(express.json());

// Mock authentication middleware for testing
app.use((req, res, next) => {
  req.user = { sub: 'test-user-123' };
  next();
});

app.use('/ai-assistant', aiRouter);

// Test suite
class AIAgentTestSuite {
  constructor() {
    this.results = {
      total: 0,
      passed: 0,
      failed: 0,
      tests: []
    };
  }

  async runTest(name, testFunction) {
    this.results.total++;
    console.log(`🧪 Running test: ${name}`);
    
    try {
      const startTime = Date.now();
      await testFunction();
      const duration = Date.now() - startTime;
      
      this.results.passed++;
      this.results.tests.push({
        name,
        status: 'PASSED',
        duration: `${duration}ms`,
        timestamp: new Date().toISOString()
      });
      
      console.log(`✅ ${name} - PASSED (${duration}ms)`);\n    } catch (error) {\n      this.results.failed++;\n      this.results.tests.push({\n        name,\n        status: 'FAILED',\n        error: error.message,\n        timestamp: new Date().toISOString()\n      });\n      \n      console.log(`❌ ${name} - FAILED: ${error.message}`);\n    }\n  }\n\n  async testDatabasePersistence() {\n    // Test conversation store initialization\n    const initialized = await conversationStore.initializeTables();\n    if (!initialized) {\n      throw new Error('Failed to initialize conversation tables');\n    }\n\n    // Test adding and retrieving messages\n    const testUserId = 'test-user-db';\n    const testConversationId = 'test-conversation';\n    const testMessage = {\n      id: Date.now(),\n      type: 'user',\n      content: 'Test database persistence',\n      timestamp: new Date()\n    };\n\n    await conversationStore.addMessage(testUserId, testConversationId, testMessage);\n    const history = await conversationStore.getHistory(testUserId, testConversationId);\n    \n    if (history.length === 0) {\n      throw new Error('Message not persisted to database');\n    }\n\n    const retrievedMessage = history[history.length - 1];\n    if (retrievedMessage.content !== testMessage.content) {\n      throw new Error('Retrieved message content does not match');\n    }\n\n    // Clean up test data\n    await conversationStore.clearHistory(testUserId, testConversationId);\n  }\n\n  async testErrorHandling() {\n    // Test error classification\n    const testErrors = [\n      { name: 'AccessDeniedException', message: 'Access denied to Bedrock' },\n      { name: 'ThrottlingException', message: 'Rate limit exceeded' },\n      { name: 'NetworkError', message: 'Network connection failed' }\n    ];\n\n    for (const testError of testErrors) {\n      const response = await aiErrorHandler.handleAIError(testError, {\n        userId: 'test-user',\n        userMessage: 'Test error handling'\n      });\n\n      if (!response.content || !response.suggestions) {\n        throw new Error(`Error handler failed for ${testError.name}`);\n      }\n    }\n\n    // Test error statistics\n    const stats = aiErrorHandler.getErrorStats();\n    if (typeof stats.totalErrors !== 'number') {\n      throw new Error('Error statistics not properly tracked');\n    }\n  }\n\n  async testAIServiceHealth() {\n    // Test Bedrock service health check\n    const bedrockHealth = await bedrockAIService.healthCheck();\n    if (!bedrockHealth.status) {\n      throw new Error('Bedrock health check returned no status');\n    }\n\n    // Test streaming service stats\n    const streamingStats = aiStreamingService.getStreamStats();\n    if (typeof streamingStats.activeStreamCount !== 'number') {\n      throw new Error('Streaming service stats invalid');\n    }\n\n    // Test conversation store stats\n    const storageStats = conversationStore.getStorageStats();\n    if (typeof storageStats.databaseAvailable !== 'boolean') {\n      throw new Error('Storage stats invalid');\n    }\n  }\n\n  async testChatEndpoint() {\n    const response = await request(app)\n      .post('/ai-assistant/chat')\n      .send({\n        message: 'Hello, test my portfolio analysis',\n        context: {\n          testMode: true\n        }\n      });\n\n    if (response.status !== 200) {\n      throw new Error(`Chat endpoint returned status ${response.status}`);\n    }\n\n    if (!response.body.success) {\n      throw new Error(`Chat endpoint failed: ${response.body.error}`);\n    }\n\n    if (!response.body.message || !response.body.message.content) {\n      throw new Error('Chat response missing content');\n    }\n\n    if (!response.body.systemInfo) {\n      throw new Error('Chat response missing system info');\n    }\n  }\n\n  async testHealthEndpoint() {\n    const response = await request(app)\n      .get('/ai-assistant/health');\n\n    if (response.status !== 200) {\n      throw new Error(`Health endpoint returned status ${response.status}`);\n    }\n\n    if (!response.body.success || !response.body.status) {\n      throw new Error('Health endpoint returned invalid response');\n    }\n\n    const requiredServices = ['bedrock', 'conversationStore', 'errorHandler', 'streaming'];\n    for (const service of requiredServices) {\n      if (!response.body.services[service]) {\n        throw new Error(`Missing health check for service: ${service}`);\n      }\n    }\n  }\n\n  async testConversationHistory() {\n    const response = await request(app)\n      .get('/ai-assistant/history?limit=10');\n\n    if (response.status !== 200) {\n      throw new Error(`History endpoint returned status ${response.status}`);\n    }\n\n    if (!response.body.success) {\n      throw new Error(`History endpoint failed: ${response.body.error}`);\n    }\n\n    if (!Array.isArray(response.body.history)) {\n      throw new Error('History response is not an array');\n    }\n\n    if (!response.body.storageStats) {\n      throw new Error('History response missing storage stats');\n    }\n  }\n\n  async runAllTests() {\n    console.log('🚀 Starting AI Agent Integration Tests\\n');\n    \n    await this.runTest('Database Persistence', () => this.testDatabasePersistence());\n    await this.runTest('Error Handling', () => this.testErrorHandling());\n    await this.runTest('AI Service Health', () => this.testAIServiceHealth());\n    await this.runTest('Chat Endpoint', () => this.testChatEndpoint());\n    await this.runTest('Health Endpoint', () => this.testHealthEndpoint());\n    await this.runTest('Conversation History', () => this.testConversationHistory());\n\n    // Print results\n    console.log('\\n📊 Test Results:');\n    console.log('================');\n    console.log(`Total Tests: ${this.results.total}`);\n    console.log(`Passed: ${this.results.passed}`);\n    console.log(`Failed: ${this.results.failed}`);\n    console.log(`Success Rate: ${((this.results.passed / this.results.total) * 100).toFixed(1)}%`);\n    \n    if (this.results.failed > 0) {\n      console.log('\\n❌ Failed Tests:');\n      this.results.tests\n        .filter(test => test.status === 'FAILED')\n        .forEach(test => {\n          console.log(`  • ${test.name}: ${test.error}`);\n        });\n    }\n\n    console.log('\\n📋 Detailed Test Results:');\n    console.table(this.results.tests);\n\n    return {\n      success: this.results.failed === 0,\n      results: this.results\n    };\n  }\n}\n\n// Run tests if this file is executed directly\nif (require.main === module) {\n  const testSuite = new AIAgentTestSuite();\n  \n  testSuite.runAllTests()\n    .then(result => {\n      if (result.success) {\n        console.log('\\n🎉 All tests passed! AI Agent is functional.');\n        process.exit(0);\n      } else {\n        console.log('\\n🚨 Some tests failed. Check the results above.');\n        process.exit(1);\n      }\n    })\n    .catch(error => {\n      console.error('\\n💥 Test suite crashed:', error);\n      process.exit(1);\n    });\n}\n\nmodule.exports = AIAgentTestSuite;"}, "new_string": "/**\n * AI Agent Integration Test\n * \n * Tests the complete AI agent functionality including:\n * - Bedrock integration\n * - Database persistence\n * - Real-time market context\n * - Error handling\n * - Response streaming capabilities\n */\n\nconst express = require('express');\nconst request = require('supertest');\n\n// Mock environment for testing\nprocess.env.AWS_REGION = 'us-east-1';\nprocess.env.NODE_ENV = 'test';\n\n// Import components to test\nconst aiRouter = require('./routes/ai-assistant');\nconst bedrockAIService = require('./utils/bedrockAIService');\nconst conversationStore = require('./utils/conversationStore');\nconst aiErrorHandler = require('./utils/aiErrorHandler');\nconst aiStreamingService = require('./utils/aiStreamingService');\n\n// Create test app\nconst app = express();\napp.use(express.json());\n\n// Mock authentication middleware for testing\napp.use((req, res, next) => {\n  req.user = { sub: 'test-user-123' };\n  next();\n});\n\napp.use('/ai-assistant', aiRouter);\n\n// Test suite\nclass AIAgentTestSuite {\n  constructor() {\n    this.results = {\n      total: 0,\n      passed: 0,\n      failed: 0,\n      tests: []\n    };\n  }\n\n  async runTest(name, testFunction) {\n    this.results.total++;\n    console.log(`🧪 Running test: ${name}`);\n    \n    try {\n      const startTime = Date.now();\n      await testFunction();\n      const duration = Date.now() - startTime;\n      \n      this.results.passed++;\n      this.results.tests.push({\n        name,\n        status: 'PASSED',\n        duration: `${duration}ms`,\n        timestamp: new Date().toISOString()\n      });\n      \n      console.log(`✅ ${name} - PASSED (${duration}ms)`);"}]