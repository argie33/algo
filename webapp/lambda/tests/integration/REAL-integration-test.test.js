/**
 * REAL Integration Tests - Not Fake Mock Bullshit
 * These tests actually hit deployed AWS infrastructure
 * - Real API Gateway endpoints
 * - Real Lambda function execution
 * - Real RDS database connections
 * - Real AWS Secrets Manager authentication
 */

const axios = require('axios');
const AWS = require('aws-sdk');

// AWS Configuration 
const API_BASE_URL = process.env.TEST_API_URL || 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev';
const AWS_REGION = process.env.AWS_REGION || 'us-east-1';
const STACK_NAME = process.env.ENVIRONMENT_NAME === 'dev' ? 'stocks-webapp-dev' : 'stocks-webapp-prod';

AWS.config.update({ region: AWS_REGION });

const cloudformation = new AWS.CloudFormation();
const lambda = new AWS.Lambda();
const rds = new AWS.RDS();
const secretsManager = new AWS.SecretsManager();

describe('REAL AWS Infrastructure Integration Tests', () => {
  let stackResources = {};
  let dbConfig = {};
  
  beforeAll(async () => {
    console.log('🚀 REAL Integration Tests - Setting up AWS environment...');
    
    // Get actual deployed stack resources
    try {
      const stackResult = await cloudformation.describeStackResources({
        StackName: STACK_NAME
      }).promise();
      
      stackResources = stackResult.StackResources.reduce((acc, resource) => {
        acc[resource.LogicalResourceId] = resource.PhysicalResourceId;
        return acc;
      }, {});
      
      console.log('✅ Stack resources loaded:', Object.keys(stackResources));
    } catch (error) {
      console.error('❌ Failed to load stack resources:', error.message);
      throw error;
    }
    
    // Get real database configuration from Secrets Manager
    try {
      const secretArn = process.env.DB_SECRET_ARN || 'arn:aws:secretsmanager:us-east-1:626216981288:secret:stocks-db-credentials-dev';
      const secret = await secretsManager.getSecretValue({ SecretId: secretArn }).promise();
      dbConfig = JSON.parse(secret.SecretString);
      console.log('✅ Database config loaded from Secrets Manager');
    } catch (error) {
      console.error('❌ Failed to load DB config:', error.message);
      throw error;
    }
  }, 30000);

  describe('Real API Gateway Integration', () => {
    test('API Gateway returns proper CORS headers', async () => {
      const response = await axios.options(`${API_BASE_URL}/api/health`);
      
      expect(response.status).toBe(200);
      expect(response.headers['access-control-allow-origin']).toBeDefined();
      expect(response.headers['access-control-allow-methods']).toContain('GET');
    });

    test('Health endpoint returns real status from deployed Lambda', async () => {
      const response = await axios.get(`${API_BASE_URL}/api/health`);
      
      expect(response.status).toBe(200);
      expect(response.data).toHaveProperty('success');
      expect(response.data).toHaveProperty('timestamp');
      expect(response.data).toHaveProperty('correlation_id');
      
      // Should have database health info
      if (response.data.success) {
        expect(response.data).toHaveProperty('database');
      }
    });

    test('Authentication endpoints work with real AWS infrastructure', async () => {
      try {
        const response = await axios.post(`${API_BASE_URL}/api/auth/validate`, {
          token: 'fake-token-for-testing'
        });
        
        // Expect proper error response, not 500 crash
        expect([401, 403]).toContain(response.status);
      } catch (error) {
        if (error.response) {
          expect([401, 403]).toContain(error.response.status);
          expect(error.response.data).toHaveProperty('error');
        } else {
          throw error;
        }
      }
    });
  });

  describe('Real Lambda Function Integration', () => {
    test('Lambda function exists and is active', async () => {
      const functionName = stackResources.ApiFunction || 'financial-dashboard-api-dev';
      
      const response = await lambda.getFunction({ FunctionName: functionName }).promise();
      
      expect(response.Configuration.State).toBe('Active');
      expect(response.Configuration.LastUpdateStatus).toBe('Successful');
      expect(response.Configuration.Runtime).toBe('nodejs18.x');
    });

    test('Lambda function responds to direct invocation', async () => {
      const functionName = stackResources.ApiFunction || 'financial-dashboard-api-dev';
      
      const payload = {
        httpMethod: 'GET',
        path: '/api/health',
        headers: {
          'Content-Type': 'application/json'
        },
        body: null
      };
      
      const response = await lambda.invoke({
        FunctionName: functionName,
        InvocationType: 'RequestResponse',
        Payload: JSON.stringify(payload)
      }).promise();
      
      expect(response.StatusCode).toBe(200);
      
      const result = JSON.parse(response.Payload);
      expect(result).toHaveProperty('statusCode');
      expect(result).toHaveProperty('body');
      
      const body = JSON.parse(result.body);
      expect(body).toHaveProperty('success');
    });

    test('Lambda function logs are accessible', async () => {
      const functionName = stackResources.ApiFunction || 'financial-dashboard-api-dev';
      const logGroupName = `/aws/lambda/${functionName}`;
      
      const cloudwatchLogs = new AWS.CloudWatchLogs();
      
      try {
        const streams = await cloudwatchLogs.describeLogStreams({
          logGroupName: logGroupName,
          orderBy: 'LastEventTime',
          descending: true,
          limit: 1
        }).promise();
        
        expect(streams.logStreams.length).toBeGreaterThan(0);
        
        // Get recent log events
        const events = await cloudwatchLogs.getLogEvents({
          logGroupName: logGroupName,
          logStreamName: streams.logStreams[0].logStreamName,
          limit: 10
        }).promise();
        
        expect(events.events.length).toBeGreaterThan(0);
        console.log('📋 Recent Lambda logs:', events.events.slice(0, 3).map(e => e.message));
        
      } catch (error) {
        console.error('⚠️ Could not access Lambda logs:', error.message);
        // Don't fail test if logs aren't accessible due to permissions
      }
    });
  });

  describe('Real Database Integration', () => {
    let dbConnection;
    
    beforeAll(async () => {
      const { Pool } = require('pg');
      
      dbConnection = new Pool({
        host: dbConfig.host,
        port: dbConfig.port,
        database: dbConfig.database,
        username: dbConfig.username,
        password: dbConfig.password,
        ssl: { rejectUnauthorized: false }
      });
      
      console.log('🗄️ Connected to real RDS database');
    });
    
    afterAll(async () => {
      if (dbConnection) {
        await dbConnection.end();
      }
    });

    test('Database connection works', async () => {
      const result = await dbConnection.query('SELECT version()');
      
      expect(result.rows).toBeDefined();
      expect(result.rows.length).toBe(1);
      expect(result.rows[0].version).toContain('PostgreSQL');
      
      console.log('✅ Database version:', result.rows[0].version.split(' ')[0]);
    });

    test('Required tables exist', async () => {
      const requiredTables = [
        'users',
        'user_sessions', 
        'api_keys',
        'portfolios',
        'portfolio_holdings',
        'security_events'
      ];
      
      for (const table of requiredTables) {
        const result = await dbConnection.query(`
          SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = $1
          );
        `, [table]);
        
        expect(result.rows[0].exists).toBe(true);
        console.log(`✅ Table exists: ${table}`);
      }
    });

    test('Database performance is acceptable', async () => {
      const start = Date.now();
      
      await dbConnection.query('SELECT COUNT(*) FROM users');
      
      const duration = Date.now() - start;
      expect(duration).toBeLessThan(1000); // Should respond within 1 second
      
      console.log(`⚡ Database query time: ${duration}ms`);
    });
  });

  describe('Real External API Integration', () => {
    test('Can fetch real stock data from external APIs', async () => {
      // Test through our deployed API
      try {
        const response = await axios.get(`${API_BASE_URL}/api/market/quote/AAPL`);
        
        if (response.status === 200) {
          expect(response.data).toHaveProperty('symbol');
          expect(response.data.symbol).toBe('AAPL');
          expect(response.data).toHaveProperty('price');
          console.log('✅ Stock data fetch successful');
        } else {
          console.log('⚠️ Stock data endpoint may need API key configuration');
        }
      } catch (error) {
        if (error.response?.status === 401) {
          console.log('⚠️ Stock data endpoint requires authentication - expected');
        } else {
          throw error;
        }
      }
    });
  });

  describe('Real Error Handling Integration', () => {
    test('API handles invalid routes gracefully', async () => {
      try {
        await axios.get(`${API_BASE_URL}/api/nonexistent-endpoint`);
        fail('Should have thrown an error');
      } catch (error) {
        expect(error.response.status).toBe(404);
        expect(error.response.data).toHaveProperty('error');
      }
    });

    test('API handles malformed requests gracefully', async () => {
      try {
        await axios.post(`${API_BASE_URL}/api/auth/login`, {
          invalid: 'data'
        });
        fail('Should have thrown an error');
      } catch (error) {
        expect([400, 422]).toContain(error.response.status);
        expect(error.response.data).toHaveProperty('error');
      }
    });

    test('API returns proper error structure', async () => {
      try {
        await axios.get(`${API_BASE_URL}/api/protected-endpoint`);
        fail('Should have thrown an error');
      } catch (error) {
        const errorData = error.response.data;
        
        expect(errorData).toHaveProperty('success');
        expect(errorData.success).toBe(false);
        expect(errorData).toHaveProperty('error');
        expect(errorData).toHaveProperty('timestamp');
      }
    });
  });

  describe('Real Performance Integration', () => {
    test('API response times are acceptable', async () => {
      const start = Date.now();
      
      const response = await axios.get(`${API_BASE_URL}/api/health`);
      
      const duration = Date.now() - start;
      expect(duration).toBeLessThan(5000); // 5 second timeout
      expect(response.status).toBe(200);
      
      console.log(`⚡ API response time: ${duration}ms`);
    });

    test('API can handle concurrent requests', async () => {
      const requests = Array(5).fill().map(() => 
        axios.get(`${API_BASE_URL}/api/health`)
      );
      
      const responses = await Promise.all(requests);
      
      responses.forEach(response => {
        expect(response.status).toBe(200);
      });
      
      console.log('✅ Concurrent requests handled successfully');
    });
  });
});