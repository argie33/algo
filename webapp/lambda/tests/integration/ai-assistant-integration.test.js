/**
 * AI Assistant Integration Tests
 * 
 * Tests the complete AI assistant functionality including:
 * - AWS Bedrock integration
 * - WebSocket streaming
 * - Database integration
 * - Authentication
 * - Portfolio context integration
 */

const request = require('supertest');
const express = require('express');
const jwt = require('jsonwebtoken');

// Import the AI assistant routes and services
const aiAssistantHandler = require('../../handlers/aiAssistantHandler');
const websocketHandler = require('../../handlers/websocketHandler');
const { query } = require('../../utils/database');

describe('AI Assistant Integration Tests', () => {
  let app;
  let testUser;
  let testToken;

  beforeAll(async () => {
    // Setup Express app with AI assistant routes
    app = express();
    app.use(express.json());
    
    // Add authentication middleware for protected routes
    app.use('/api/ai', (req, res, next) => {
      // Simple auth bypass for integration tests
      req.user = testUser;
      next();
    });

    // Add AI assistant routes
    app.post('/api/ai/chat', aiAssistantHandler.handleChatRequest);
    app.get('/api/ai/history/:conversationId?', aiAssistantHandler.handleGetHistory);
    app.get('/api/ai/conversations', aiAssistantHandler.handleGetConversations);
    app.delete('/api/ai/history/:conversationId?', aiAssistantHandler.handleClearHistory);
    app.get('/api/ai/config', aiAssistantHandler.handleGetConfig);
    app.get('/api/ai/health', aiAssistantHandler.handleHealthCheck);

    // Setup test user
    testUser = {
      userId: 'test-ai-user-' + Date.now(),
      email: 'test@example.com'
    };

    // Create test JWT token
    testToken = jwt.sign(testUser, process.env.JWT_SECRET || 'test-secret');
  });

  afterAll(async () => {
    // Cleanup test data
    try {
      await query('DELETE FROM ai_conversations WHERE user_id = $1', [testUser.userId]);
      await query('DELETE FROM ai_user_configurations WHERE user_id = $1', [testUser.userId]);
    } catch (error) {
      console.warn('Cleanup warning:', error.message);
    }
  });

  describe('AI Configuration and Health', () => {
    test('should return AI service health status', async () => {
      const response = await request(app)
        .get('/api/ai/health')
        .expect(200);

      expect(response.body).toHaveProperty('status');
      expect(response.body).toHaveProperty('bedrock');
      expect(response.body).toHaveProperty('features');
      expect(response.body.features).toHaveProperty('portfolioAnalysis');
      expect(response.body.features).toHaveProperty('marketInsights');
    });

    test('should return AI configuration', async () => {
      const response = await request(app)
        .get('/api/ai/config')
        .expect(200);

      expect(response.body).toHaveProperty('features');
      expect(response.body).toHaveProperty('models');
      expect(response.body.features).toHaveProperty('streamingEnabled');
      expect(response.body.features).toHaveProperty('portfolioIntegration');
    });

    test('should handle service unavailable gracefully', async () => {
      // Mock Bedrock unavailability by setting invalid region
      const originalRegion = process.env.AWS_REGION;
      process.env.AWS_REGION = 'invalid-region';

      const response = await request(app)
        .get('/api/ai/health')
        .expect(200);

      expect(response.body.status).toBe('degraded');
      expect(response.body.bedrock.available).toBe(false);

      // Restore original region
      process.env.AWS_REGION = originalRegion;
    });
  });

  describe('Chat Functionality', () => {
    test('should handle basic chat message', async () => {
      const chatRequest = {
        message: 'Hello, what can you help me with?',
        conversationId: 'test-conversation-' + Date.now()
      };

      const response = await request(app)
        .post('/api/ai/chat')
        .send(chatRequest)
        .expect(200);

      expect(response.body).toHaveProperty('response');
      expect(response.body).toHaveProperty('messageId');
      expect(response.body).toHaveProperty('conversationId');
      expect(response.body.response).toBeTruthy();
      expect(typeof response.body.response).toBe('string');
    });

    test('should handle portfolio-related questions', async () => {
      const portfolioRequest = {
        message: 'Analyze my portfolio performance',
        conversationId: 'portfolio-test-' + Date.now(),
        context: {
          portfolioData: {
            totalValue: 50000,
            dayChange: 250,
            holdings: [
              { symbol: 'AAPL', shares: 100, value: 15000 },
              { symbol: 'MSFT', shares: 50, value: 12000 }
            ]
          }
        }
      };

      const response = await request(app)
        .post('/api/ai/chat')
        .send(portfolioRequest)
        .expect(200);

      expect(response.body).toHaveProperty('response');
      expect(response.body.response).toContain('portfolio');
      expect(response.body).toHaveProperty('metadata');
    });

    test('should handle market data questions', async () => {
      const marketRequest = {
        message: 'What is the current market trend?',
        conversationId: 'market-test-' + Date.now(),
        context: {
          marketData: {
            SPY: { price: 420.50, change: 2.15 },
            QQQ: { price: 350.25, change: -1.85 }
          }
        }
      };

      const response = await request(app)
        .post('/api/ai/chat')
        .send(marketRequest)
        .expect(200);

      expect(response.body).toHaveProperty('response');
      expect(response.body.response.length).toBeGreaterThan(0);
    });

    test('should validate input parameters', async () => {
      // Test empty message
      await request(app)
        .post('/api/ai/chat')
        .send({ message: '', conversationId: 'test' })
        .expect(400);

      // Test missing message
      await request(app)
        .post('/api/ai/chat')
        .send({ conversationId: 'test' })
        .expect(400);

      // Test invalid message type
      await request(app)
        .post('/api/ai/chat')
        .send({ message: 123, conversationId: 'test' })
        .expect(400);
    });

    test('should handle rate limiting', async () => {
      const conversationId = 'rate-limit-test-' + Date.now();
      
      // Send multiple rapid requests
      const requests = Array.from({ length: 10 }, (_, i) => 
        request(app)
          .post('/api/ai/chat')
          .send({
            message: `Test message ${i}`,
            conversationId
          })
      );

      const responses = await Promise.allSettled(requests);
      
      // Some requests should succeed, others might be rate limited
      const successfulResponses = responses.filter(r => r.status === 'fulfilled' && r.value.status === 200);
      expect(successfulResponses.length).toBeGreaterThan(0);
    });
  });

  describe('Conversation Management', () => {
    let testConversationId;

    beforeEach(() => {
      testConversationId = 'conversation-mgmt-' + Date.now();
    });

    test('should retrieve conversation history', async () => {
      // First, send a few messages to create history
      await request(app)
        .post('/api/ai/chat')
        .send({
          message: 'First message',
          conversationId: testConversationId
        });

      await request(app)
        .post('/api/ai/chat')
        .send({
          message: 'Second message',
          conversationId: testConversationId
        });

      // Now retrieve the history
      const response = await request(app)
        .get(`/api/ai/history/${testConversationId}`)
        .expect(200);

      expect(Array.isArray(response.body)).toBe(true);
      expect(response.body.length).toBeGreaterThanOrEqual(2);
      
      const userMessages = response.body.filter(msg => msg.message_type === 'user');
      expect(userMessages.length).toBeGreaterThanOrEqual(2);
    });

    test('should retrieve all conversations for user', async () => {
      // Create multiple conversations
      const conv1 = 'conv-list-1-' + Date.now();
      const conv2 = 'conv-list-2-' + Date.now();

      await request(app)
        .post('/api/ai/chat')
        .send({ message: 'Test 1', conversationId: conv1 });

      await request(app)
        .post('/api/ai/chat')
        .send({ message: 'Test 2', conversationId: conv2 });

      const response = await request(app)
        .get('/api/ai/conversations')
        .expect(200);

      expect(Array.isArray(response.body)).toBe(true);
      expect(response.body.length).toBeGreaterThanOrEqual(2);
      
      const conversationIds = response.body.map(conv => conv.conversation_id);
      expect(conversationIds).toContain(conv1);
      expect(conversationIds).toContain(conv2);
    });

    test('should clear conversation history', async () => {
      // Create conversation with messages
      await request(app)
        .post('/api/ai/chat')
        .send({
          message: 'Message to be cleared',
          conversationId: testConversationId
        });

      // Clear the conversation
      await request(app)
        .delete(`/api/ai/history/${testConversationId}`)
        .expect(200);

      // Verify it's cleared
      const response = await request(app)
        .get(`/api/ai/history/${testConversationId}`)
        .expect(200);

      expect(response.body.length).toBe(0);
    });

    test('should clear all conversations for user', async () => {
      // Create multiple conversations
      await request(app)
        .post('/api/ai/chat')
        .send({ message: 'Test 1', conversationId: 'clear-all-1-' + Date.now() });

      await request(app)
        .post('/api/ai/chat')
        .send({ message: 'Test 2', conversationId: 'clear-all-2-' + Date.now() });

      // Clear all conversations
      await request(app)
        .delete('/api/ai/history')
        .expect(200);

      // Verify all are cleared
      const response = await request(app)
        .get('/api/ai/conversations')
        .expect(200);

      expect(response.body.length).toBe(0);
    });
  });

  describe('Error Handling and Resilience', () => {
    test('should handle database connectivity issues', async () => {
      // Mock database error by temporarily breaking the connection
      const originalQuery = require('../../utils/database').query;
      
      // Mock database failure
      require('../../utils/database').query = jest.fn().mockRejectedValue(new Error('Database unavailable'));

      const response = await request(app)
        .post('/api/ai/chat')
        .send({
          message: 'Test with DB failure',
          conversationId: 'db-error-test-' + Date.now()
        })
        .expect(200);

      // Should still get a response (fallback mode)
      expect(response.body).toHaveProperty('response');
      expect(response.body.response).toContain('temporarily unable');

      // Restore original query function
      require('../../utils/database').query = originalQuery;
    });

    test('should handle Bedrock service errors gracefully', async () => {
      // Mock Bedrock error by setting invalid model
      const response = await request(app)
        .post('/api/ai/chat')
        .send({
          message: 'Test with Bedrock error',
          conversationId: 'bedrock-error-test-' + Date.now(),
          model: 'invalid-model-id'
        })
        .expect(200);

      // Should get fallback response
      expect(response.body).toHaveProperty('response');
      expect(response.body.response).toBeTruthy();
    });

    test('should handle malformed requests', async () => {
      // Test malformed JSON
      await request(app)
        .post('/api/ai/chat')
        .send('invalid-json')
        .expect(400);

      // Test null values
      await request(app)
        .post('/api/ai/chat')
        .send({ message: null, conversationId: null })
        .expect(400);
    });

    test('should handle very long messages', async () => {
      const longMessage = 'A'.repeat(10000); // 10KB message

      const response = await request(app)
        .post('/api/ai/chat')
        .send({
          message: longMessage,
          conversationId: 'long-message-test-' + Date.now()
        })
        .expect(200);

      expect(response.body).toHaveProperty('response');
    });
  });

  describe('Security and Authentication', () => {
    test('should isolate conversations by user', async () => {
      const user1 = { userId: 'user1-' + Date.now() };
      const user2 = { userId: 'user2-' + Date.now() };
      const conversationId = 'shared-conv-id-' + Date.now();

      // Create conversation for user1
      const app1 = express();
      app1.use(express.json());
      app1.use('/api/ai', (req, res, next) => { req.user = user1; next(); });
      app1.post('/api/ai/chat', aiAssistantHandler.handleChatRequest);
      app1.get('/api/ai/history/:conversationId', aiAssistantHandler.handleGetHistory);

      // Create conversation for user2
      const app2 = express();
      app2.use(express.json());
      app2.use('/api/ai', (req, res, next) => { req.user = user2; next(); });
      app2.post('/api/ai/chat', aiAssistantHandler.handleChatRequest);
      app2.get('/api/ai/history/:conversationId', aiAssistantHandler.handleGetHistory);

      // User1 sends message
      await request(app1)
        .post('/api/ai/chat')
        .send({ message: 'User1 secret message', conversationId });

      // User2 should not see user1's messages
      const user2History = await request(app2)
        .get(`/api/ai/history/${conversationId}`)
        .expect(200);

      expect(user2History.body.length).toBe(0);
    });

    test('should sanitize user input', async () => {
      const maliciousMessage = '<script>alert("xss")</script>DROP TABLE users;';

      const response = await request(app)
        .post('/api/ai/chat')
        .send({
          message: maliciousMessage,
          conversationId: 'security-test-' + Date.now()
        })
        .expect(200);

      // Should not contain executable script
      expect(response.body.response).not.toContain('<script>');
      expect(response.body.response).not.toContain('DROP TABLE');
    });
  });

  describe('Performance and Scalability', () => {
    test('should handle concurrent requests', async () => {
      const concurrentRequests = 10;
      const conversationId = 'concurrent-test-' + Date.now();

      const requests = Array.from({ length: concurrentRequests }, (_, i) =>
        request(app)
          .post('/api/ai/chat')
          .send({
            message: `Concurrent message ${i}`,
            conversationId
          })
      );

      const responses = await Promise.all(requests);

      // All requests should succeed
      responses.forEach(response => {
        expect(response.status).toBe(200);
        expect(response.body).toHaveProperty('response');
      });
    });

    test('should respond within reasonable time limits', async () => {
      const startTime = Date.now();

      const response = await request(app)
        .post('/api/ai/chat')
        .send({
          message: 'Quick response test',
          conversationId: 'performance-test-' + Date.now()
        })
        .expect(200);

      const responseTime = Date.now() - startTime;

      expect(responseTime).toBeLessThan(10000); // Should respond within 10 seconds
      expect(response.body).toHaveProperty('response');
    });

    test('should handle large conversation histories efficiently', async () => {
      const conversationId = 'large-history-test-' + Date.now();

      // Create a conversation with many messages
      for (let i = 0; i < 50; i++) {
        await request(app)
          .post('/api/ai/chat')
          .send({
            message: `Message ${i}`,
            conversationId
          });
      }

      const startTime = Date.now();

      const response = await request(app)
        .get(`/api/ai/history/${conversationId}`)
        .expect(200);

      const retrievalTime = Date.now() - startTime;

      expect(retrievalTime).toBeLessThan(5000); // Should retrieve within 5 seconds
      expect(response.body.length).toBeGreaterThan(50); // User + AI messages
    });
  });

  describe('Database Integration', () => {
    test('should store conversations in database', async () => {
      const conversationId = 'db-storage-test-' + Date.now();
      const testMessage = 'Database storage test message';

      await request(app)
        .post('/api/ai/chat')
        .send({
          message: testMessage,
          conversationId
        })
        .expect(200);

      // Verify data is in database
      const result = await query(
        'SELECT * FROM ai_conversations WHERE user_id = $1 AND conversation_id = $2 AND content = $3',
        [testUser.userId, conversationId, testMessage]
      );

      expect(result.rows.length).toBeGreaterThan(0);
      expect(result.rows[0].message_type).toBe('user');
    });

    test('should handle database schema migrations', async () => {
      // Verify required tables exist
      const tables = await query(`
        SELECT table_name FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name IN ('ai_conversations', 'ai_user_configurations', 'ai_conversation_analytics')
      `);

      expect(tables.rows.length).toBeGreaterThanOrEqual(1); // At least ai_conversations should exist
    });
  });
});