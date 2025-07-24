/**
 * Real AWS Services Integration Tests
 * Tests actual AWS services without mocks or placeholders
 */

const AWS = require('aws-sdk');
const axios = require('axios');
const { expect } = require('chai');
const { v4: uuidv4 } = require('uuid');

// Configure AWS SDK for integration testing
AWS.config.update({
    region: process.env.AWS_REGION || 'us-east-1'
});

// Initialize AWS service clients
const secretsManager = new AWS.SecretsManager();
const rds = new AWS.RDS();
const s3 = new AWS.S3();
const sqs = new AWS.SQS();
const sns = new AWS.SNS();
const cognito = new AWS.CognitoIdentityServiceProvider();
const lambda = new AWS.Lambda();

// Test configuration from environment
const testConfig = {
    dbEndpoint: process.env.INTEGRATION_TEST_DB_ENDPOINT,
    dbSecretArn: process.env.INTEGRATION_TEST_DB_SECRET_ARN,
    cognitoPoolId: process.env.INTEGRATION_TEST_COGNITO_POOL_ID,
    cognitoClientId: process.env.INTEGRATION_TEST_COGNITO_CLIENT_ID,
    s3Bucket: process.env.INTEGRATION_TEST_S3_BUCKET,
    redisEndpoint: process.env.INTEGRATION_TEST_REDIS_ENDPOINT,
    sqsQueueUrl: process.env.INTEGRATION_TEST_SQS_QUEUE_URL,
    snsTopicArn: process.env.INTEGRATION_TEST_SNS_TOPIC_ARN,
    apiBaseUrl: process.env.INTEGRATION_TEST_API_URL || 'https://api.dev.example.com'
};

// Helper functions
const getDbCredentials = async () => {
    try {
        const secret = await secretsManager.getSecretValue({
            SecretId: testConfig.dbSecretArn
        }).promise();
        return JSON.parse(secret.SecretString);
    } catch (error) {
        throw new Error(`Failed to get database credentials: ${error.message}`);
    }
};

const createTestUser = async (username, email, password) => {
    try {
        const params = {
            UserPoolId: testConfig.cognitoPoolId,
            Username: username,
            UserAttributes: [
                { Name: 'email', Value: email },
                { Name: 'email_verified', Value: 'true' }
            ],
            TemporaryPassword: password,
            MessageAction: 'SUPPRESS'
        };
        
        const result = await cognito.adminCreateUser(params).promise();
        
        // Set permanent password
        await cognito.adminSetUserPassword({
            UserPoolId: testConfig.cognitoPoolId,
            Username: username,
            Password: password,
            Permanent: true
        }).promise();
        
        return result.User;
    } catch (error) {
        if (error.code !== 'UsernameExistsException') {
            throw error;
        }
        // User already exists, continue with tests
        return { Username: username };
    }
};

const authenticateUser = async (username, password) => {
    try {
        const params = {
            AuthFlow: 'USER_PASSWORD_AUTH',
            ClientId: testConfig.cognitoClientId,
            AuthParameters: {
                USERNAME: username,
                PASSWORD: password
            }
        };
        
        const result = await cognito.initiateAuth(params).promise();
        return result.AuthenticationResult;
    } catch (error) {
        throw new Error(`Authentication failed: ${error.message}`);
    }
};

const cleanupTestUser = async (username) => {
    try {
        await cognito.adminDeleteUser({
            UserPoolId: testConfig.cognitoPoolId,
            Username: username
        }).promise();
    } catch (error) {
        // Ignore errors during cleanup
        console.warn(`Failed to cleanup user ${username}:`, error.message);
    }
};

describe('Real AWS Services Integration Tests', function() {
    this.timeout(60000); // 60 second timeout for AWS operations
    
    let testUserId;
    let testUserToken;
    let createdResources = [];
    
    before(async function() {
        console.log('Setting up integration test environment...');
        
        // Verify all required environment variables
        const requiredEnvVars = [
            'INTEGRATION_TEST_DB_ENDPOINT',
            'INTEGRATION_TEST_DB_SECRET_ARN',
            'INTEGRATION_TEST_COGNITO_POOL_ID',
            'INTEGRATION_TEST_COGNITO_CLIENT_ID',
            'INTEGRATION_TEST_S3_BUCKET'
        ];
        
        for (const envVar of requiredEnvVars) {
            if (!process.env[envVar]) {
                throw new Error(`Required environment variable ${envVar} is not set`);
            }
        }
        
        // Create test user for authentication tests
        testUserId = `test-user-${uuidv4()}`;
        const testEmail = `${testUserId}@example.com`;
        const testPassword = 'TempPassword123!';
        
        await createTestUser(testUserId, testEmail, testPassword);
        const authResult = await authenticateUser(testUserId, testPassword);
        testUserToken = authResult.AccessToken;
        
        console.log('Integration test environment setup complete');
    });
    
    after(async function() {
        console.log('Cleaning up integration test resources...');
        
        // Cleanup test user
        if (testUserId) {
            await cleanupTestUser(testUserId);
        }
        
        // Cleanup created S3 objects
        if (createdResources.length > 0) {
            const deleteParams = {
                Bucket: testConfig.s3Bucket,
                Delete: {
                    Objects: createdResources.map(key => ({ Key: key }))
                }
            };
            
            try {
                await s3.deleteObjects(deleteParams).promise();
            } catch (error) {
                console.warn('Failed to cleanup S3 objects:', error.message);
            }
        }
        
        console.log('Integration test cleanup complete');
    });
    
    describe('Database Integration', function() {
        let dbConnection;
        
        it('should connect to real RDS PostgreSQL database', async function() {
            const credentials = await getDbCredentials();
            expect(credentials).to.have.property('username');
            expect(credentials).to.have.property('password');
            
            // Test connection using pg client
            const { Client } = require('pg');
            dbConnection = new Client({
                host: testConfig.dbEndpoint,
                port: 5432,
                database: 'integration_test_db',
                user: credentials.username,
                password: credentials.password,
                ssl: { rejectUnauthorized: false }
            });
            
            await dbConnection.connect();
            const result = await dbConnection.query('SELECT NOW()');
            expect(result.rows).to.have.length(1);
        });
        
        it('should perform CRUD operations on real database', async function() {
            const testPortfolioId = uuidv4();
            
            // Create
            await dbConnection.query(
                'INSERT INTO test_portfolios (user_id, portfolio_name, total_value) VALUES ($1, $2, $3)',
                [testUserId, 'Integration Test Portfolio', 15000.00]
            );
            
            // Read
            const readResult = await dbConnection.query(
                'SELECT * FROM test_portfolios WHERE user_id = $1',
                [testUserId]
            );
            expect(readResult.rows).to.have.length(1);
            expect(readResult.rows[0].portfolio_name).to.equal('Integration Test Portfolio');
            
            // Update
            await dbConnection.query(
                'UPDATE test_portfolios SET total_value = $1 WHERE user_id = $2',
                [20000.00, testUserId]
            );
            
            const updateResult = await dbConnection.query(
                'SELECT total_value FROM test_portfolios WHERE user_id = $1',
                [testUserId]
            );
            expect(parseFloat(updateResult.rows[0].total_value)).to.equal(20000.00);
            
            // Delete
            await dbConnection.query(
                'DELETE FROM test_portfolios WHERE user_id = $1',
                [testUserId]
            );
            
            const deleteResult = await dbConnection.query(
                'SELECT * FROM test_portfolios WHERE user_id = $1',
                [testUserId]
            );
            expect(deleteResult.rows).to.have.length(0);
        });
        
        after(async function() {
            if (dbConnection) {
                await dbConnection.end();
            }
        });
    });
    
    describe('Cognito Authentication Integration', function() {
        it('should authenticate user with real Cognito', async function() {
            expect(testUserToken).to.be.a('string');
            expect(testUserToken.length).to.be.greaterThan(0);
        });
        
        it('should validate JWT token from Cognito', async function() {
            // Decode JWT header to verify it's from Cognito
            const [header] = testUserToken.split('.');
            const decodedHeader = JSON.parse(Buffer.from(header, 'base64').toString());
            
            expect(decodedHeader).to.have.property('alg', 'RS256');
            expect(decodedHeader).to.have.property('kid');
        });
        
        it('should retrieve user attributes from Cognito', async function() {
            const userResult = await cognito.adminGetUser({
                UserPoolId: testConfig.cognitoPoolId,
                Username: testUserId
            }).promise();
            
            expect(userResult.Username).to.equal(testUserId);
            expect(userResult.UserAttributes).to.be.an('array');
            
            const emailAttr = userResult.UserAttributes.find(attr => attr.Name === 'email');
            expect(emailAttr).to.exist;
            expect(emailAttr.Value).to.contain('@example.com');
        });
    });
    
    describe('S3 Integration', function() {
        it('should upload and retrieve files from real S3', async function() {
            const testKey = `integration-test/${uuidv4()}.json`;
            const testData = {
                testId: uuidv4(),
                timestamp: new Date().toISOString(),
                message: 'Integration test data'
            };
            
            // Upload
            await s3.putObject({
                Bucket: testConfig.s3Bucket,
                Key: testKey,
                Body: JSON.stringify(testData),
                ContentType: 'application/json'
            }).promise();
            
            createdResources.push(testKey);
            
            // Retrieve
            const getResult = await s3.getObject({
                Bucket: testConfig.s3Bucket,
                Key: testKey
            }).promise();
            
            const retrievedData = JSON.parse(getResult.Body.toString());
            expect(retrievedData).to.deep.equal(testData);
        });
        
        it('should list objects in S3 bucket', async function() {
            const listResult = await s3.listObjectsV2({
                Bucket: testConfig.s3Bucket,
                Prefix: 'integration-test/'
            }).promise();
            
            expect(listResult.Contents).to.be.an('array');
            expect(listResult.Contents.length).to.be.greaterThan(0);
        });
    });
    
    describe('SQS Integration', function() {
        it('should send and receive messages from real SQS', async function() {
            const testMessage = {
                id: uuidv4(),
                type: 'integration-test',
                data: { userId: testUserId, timestamp: Date.now() }
            };
            
            // Send message
            const sendResult = await sqs.sendMessage({
                QueueUrl: testConfig.sqsQueueUrl,
                MessageBody: JSON.stringify(testMessage)
            }).promise();
            
            expect(sendResult.MessageId).to.be.a('string');
            
            // Receive message
            const receiveResult = await sqs.receiveMessage({
                QueueUrl: testConfig.sqsQueueUrl,
                MaxNumberOfMessages: 1,
                WaitTimeSeconds: 5
            }).promise();
            
            expect(receiveResult.Messages).to.be.an('array');
            expect(receiveResult.Messages.length).to.be.greaterThan(0);
            
            const receivedMessage = JSON.parse(receiveResult.Messages[0].Body);
            expect(receivedMessage.id).to.equal(testMessage.id);
            
            // Delete message
            await sqs.deleteMessage({
                QueueUrl: testConfig.sqsQueueUrl,
                ReceiptHandle: receiveResult.Messages[0].ReceiptHandle
            }).promise();
        });
    });
    
    describe('SNS Integration', function() {
        it('should publish message to real SNS topic', async function() {
            const testMessage = {
                type: 'integration-test-notification',
                userId: testUserId,
                timestamp: new Date().toISOString()
            };
            
            const publishResult = await sns.publish({
                TopicArn: testConfig.snsTopicArn,
                Message: JSON.stringify(testMessage),
                Subject: 'Integration Test Notification'
            }).promise();
            
            expect(publishResult.MessageId).to.be.a('string');
        });
    });
    
    describe('API Gateway Integration', function() {
        it('should call real API endpoints with authentication', async function() {
            try {
                const response = await axios.get(`${testConfig.apiBaseUrl}/health`, {
                    headers: {
                        'Authorization': `Bearer ${testUserToken}`,
                        'Content-Type': 'application/json'
                    },
                    timeout: 30000
                });
                
                expect(response.status).to.equal(200);
                expect(response.data).to.have.property('status');
            } catch (error) {
                if (error.code === 'ENOTFOUND' || error.code === 'ECONNREFUSED') {
                    console.warn('API endpoint not available, skipping test');
                    this.skip();
                } else {
                    throw error;
                }
            }
        });
        
        it('should handle API authentication errors correctly', async function() {
            try {
                await axios.get(`${testConfig.apiBaseUrl}/protected-endpoint`, {
                    headers: {
                        'Authorization': 'Bearer invalid-token',
                        'Content-Type': 'application/json'
                    },
                    timeout: 10000
                });
                
                // Should not reach here
                expect.fail('Expected authentication error');
            } catch (error) {
                if (error.code === 'ENOTFOUND' || error.code === 'ECONNREFUSED') {
                    console.warn('API endpoint not available, skipping test');
                    this.skip();
                } else if (error.response) {
                    expect(error.response.status).to.be.oneOf([401, 403]);
                } else {
                    throw error;
                }
            }
        });
    });
    
    describe('Cross-Service Integration', function() {
        it('should perform end-to-end portfolio operation', async function() {
            const portfolioData = {
                userId: testUserId,
                portfolioName: 'E2E Test Portfolio',
                initialValue: 25000.00,
                assets: [
                    { symbol: 'AAPL', shares: 10, price: 150.00 },
                    { symbol: 'GOOGL', shares: 5, price: 2500.00 }
                ]
            };
            
            // Step 1: Store portfolio data in S3
            const s3Key = `portfolios/${testUserId}/${uuidv4()}.json`;
            await s3.putObject({
                Bucket: testConfig.s3Bucket,
                Key: s3Key,
                Body: JSON.stringify(portfolioData),
                ContentType: 'application/json'
            }).promise();
            
            createdResources.push(s3Key);
            
            // Step 2: Send notification via SNS
            await sns.publish({
                TopicArn: testConfig.snsTopicArn,
                Message: JSON.stringify({
                    event: 'portfolio_created',
                    userId: testUserId,
                    s3Key: s3Key
                }),
                Subject: 'Portfolio Created'
            }).promise();
            
            // Step 3: Queue processing message via SQS
            await sqs.sendMessage({
                QueueUrl: testConfig.sqsQueueUrl,
                MessageBody: JSON.stringify({
                    action: 'process_portfolio',
                    userId: testUserId,
                    s3Key: s3Key
                })
            }).promise();
            
            // Step 4: Verify data integrity
            const retrievedData = await s3.getObject({
                Bucket: testConfig.s3Bucket,
                Key: s3Key
            }).promise();
            
            const storedPortfolio = JSON.parse(retrievedData.Body.toString());
            expect(storedPortfolio.userId).to.equal(testUserId);
            expect(storedPortfolio.assets).to.have.length(2);
            
            // Calculate expected total value
            const expectedValue = portfolioData.assets.reduce(
                (total, asset) => total + (asset.shares * asset.price), 
                0
            );
            expect(expectedValue).to.equal(14000.00); // 10*150 + 5*2500 = 1500 + 12500
        });
    });
    
    describe('Performance and Load Testing', function() {
        it('should handle concurrent database operations', async function() {
            const credentials = await getDbCredentials();
            const concurrentOperations = 10;
            const operations = [];
            
            for (let i = 0; i < concurrentOperations; i++) {
                operations.push((async () => {
                    const { Client } = require('pg');
                    const client = new Client({
                        host: testConfig.dbEndpoint,
                        port: 5432,
                        database: 'integration_test_db',
                        user: credentials.username,
                        password: credentials.password,
                        ssl: { rejectUnauthorized: false }
                    });
                    
                    await client.connect();
                    const result = await client.query('SELECT $1 as test_value', [i]);
                    await client.end();
                    
                    return result.rows[0].test_value;
                })());
            }
            
            const results = await Promise.all(operations);
            expect(results).to.have.length(concurrentOperations);
            expect(results).to.include.members([0, 1, 2, 3, 4, 5, 6, 7, 8, 9]);
        });
        
        it('should handle high-volume S3 operations', async function() {
            const batchSize = 5;
            const uploadPromises = [];
            
            for (let i = 0; i < batchSize; i++) {
                const key = `load-test/${uuidv4()}.json`;
                const data = { 
                    index: i, 
                    timestamp: Date.now(),
                    data: 'a'.repeat(1000) // 1KB of data
                };
                
                uploadPromises.push(
                    s3.putObject({
                        Bucket: testConfig.s3Bucket,
                        Key: key,
                        Body: JSON.stringify(data),
                        ContentType: 'application/json'
                    }).promise()
                );
                
                createdResources.push(key);
            }
            
            const startTime = Date.now();
            await Promise.all(uploadPromises);
            const endTime = Date.now();
            
            const duration = endTime - startTime;
            console.log(`Uploaded ${batchSize} objects in ${duration}ms`);
            
            // Should complete within reasonable time (adjust threshold as needed)
            expect(duration).to.be.lessThan(10000); // 10 seconds
        });
    });
});

// Export for use in other test files
module.exports = {
    testConfig,
    getDbCredentials,
    createTestUser,
    authenticateUser,
    cleanupTestUser
};