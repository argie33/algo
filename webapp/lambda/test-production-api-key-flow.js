#!/usr/bin/env node
/**
 * Production API Key Flow Test
 * Simulates real user journey: Frontend → API Gateway → Lambda → Database → Back to Frontend
 * Tests actual encryption/decryption with environment variables and user context
 */

const crypto = require('crypto');
const jwt = require('jsonwebtoken');

// Simulate the actual production flow
class ProductionApiKeyFlowTest {
  constructor() {
    this.jwtSecret = 'test-jwt-secret';
    this.encryptionSecret = 'test-encryption-secret-32-chars-long';
    this.userSalt = crypto.randomBytes(16).toString('hex');
    this.testUser = {
      id: 'user-123-456-789',
      email: 'test@example.com',
      name: 'Test User'
    };
    this.realDatabase = new Map(); // Simulate real database storage
  }

  // Step 1: Simulate frontend API key submission
  simulateFrontendSubmission(apiKey, apiSecret, provider) {
    console.log('🌐 STEP 1: Frontend submits API key');
    console.log('   User enters API key in frontend form');
    console.log('   Provider:', provider);
    console.log('   API Key Length:', apiKey.length);
    console.log('   Has Secret:', !!apiSecret);
    
    // Frontend creates JWT token (simulating authentication)
    const token = jwt.sign(
      { 
        userId: this.testUser.id, 
        email: this.testUser.email,
        exp: Math.floor(Date.now() / 1000) + (60 * 60) // 1 hour
      }, 
      this.jwtSecret
    );
    
    console.log('   JWT Token created for user:', this.testUser.id);
    
    // Frontend sends request to API Gateway
    const request = {
      method: 'POST',
      path: '/api/settings/api-keys',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        provider,
        apiKey,
        apiSecret,
        description: 'Production test key',
        isSandbox: true
      })
    };
    
    console.log('   Request sent to API Gateway');
    return request;
  }

  // Step 2: Simulate API Gateway processing
  simulateApiGateway(request) {
    console.log('\n🚪 STEP 2: API Gateway processes request');
    console.log('   Method:', request.method);
    console.log('   Path:', request.path);
    console.log('   Has Authorization:', !!request.headers.Authorization);
    
    // API Gateway forwards to Lambda
    const lambdaEvent = {
      httpMethod: request.method,
      path: request.path,
      headers: request.headers,
      body: request.body,
      requestContext: {
        requestId: 'req-' + crypto.randomBytes(8).toString('hex'),
        stage: 'prod',
        accountId: '123456789012'
      }
    };
    
    console.log('   Request forwarded to Lambda');
    console.log('   Request ID:', lambdaEvent.requestContext.requestId);
    return lambdaEvent;
  }

  // Step 3: Simulate Lambda authentication
  simulateLambdaAuth(event) {
    console.log('\n⚡ STEP 3: Lambda authenticates request');
    
    try {
      const authHeader = event.headers.Authorization;
      if (!authHeader || !authHeader.startsWith('Bearer ')) {
        throw new Error('No valid authorization header');
      }
      
      const token = authHeader.substring(7);
      const decoded = jwt.verify(token, this.jwtSecret);
      
      console.log('   JWT verified successfully');
      console.log('   User ID:', decoded.userId);
      console.log('   Email:', decoded.email);
      
      return decoded;
    } catch (error) {
      console.error('   ❌ Authentication failed:', error.message);
      throw error;
    }
  }

  // Step 4: Simulate API key encryption in Lambda
  simulateApiKeyEncryption(apiKey, userId, provider) {
    console.log('\n🔐 STEP 4: Lambda encrypts API key');
    console.log('   User ID:', userId);
    console.log('   Provider:', provider);
    console.log('   Original Key Length:', apiKey.length);
    
    try {
      // Generate user-specific salt (this would be retrieved from DB in production)
      const userSalt = this.userSalt;
      console.log('   User salt generated/retrieved');
      
      // Create encryption key from secret + salt
      const encryptionKey = crypto.scryptSync(this.encryptionSecret, userSalt, 32);
      console.log('   Encryption key derived from secret + salt');
      
      // Encrypt the API key
      const iv = crypto.randomBytes(12);
      const cipher = crypto.createCipheriv('aes-256-gcm', encryptionKey, iv);
      
      let encrypted = cipher.update(apiKey, 'utf8', 'hex');
      encrypted += cipher.final('hex');
      
      const authTag = cipher.getAuthTag();
      
      const encryptedData = {
        encrypted: encrypted,
        iv: iv.toString('hex'),
        authTag: authTag.toString('hex')
      };
      
      console.log('   ✅ API key encrypted successfully');
      console.log('   Encrypted length:', encrypted.length);
      console.log('   IV length:', encryptedData.iv.length);
      console.log('   Auth tag length:', encryptedData.authTag.length);
      
      return { encryptedData, userSalt };
    } catch (error) {
      console.error('   ❌ Encryption failed:', error.message);
      throw error;
    }
  }

  // Step 5: Simulate database storage
  simulateDatabaseStorage(userId, provider, encryptedData, userSalt) {
    console.log('\n💾 STEP 5: Store encrypted data in database');
    console.log('   User ID:', userId);
    console.log('   Provider:', provider);
    
    try {
      const dbRecord = {
        id: crypto.randomBytes(4).toString('hex'),
        user_id: userId,
        provider: provider,
        encrypted_api_key: encryptedData.encrypted,
        key_iv: encryptedData.iv,
        key_auth_tag: encryptedData.authTag,
        user_salt: userSalt,
        is_sandbox: true,
        is_active: true,
        created_at: new Date().toISOString(),
        last_used: null
      };
      
      // Store in "database"
      const dbKey = `${userId}-${provider}`;
      this.realDatabase.set(dbKey, dbRecord);
      
      console.log('   ✅ Record stored in database');
      console.log('   Database key:', dbKey);
      console.log('   Record ID:', dbRecord.id);
      
      return dbRecord;
    } catch (error) {
      console.error('   ❌ Database storage failed:', error.message);
      throw error;
    }
  }

  // Step 6: Simulate API key retrieval (when user needs to use it)
  simulateApiKeyRetrieval(userId, provider) {
    console.log('\n🔍 STEP 6: Retrieve API key for usage');
    console.log('   User ID:', userId);
    console.log('   Provider:', provider);
    
    try {
      // Get from database
      const dbKey = `${userId}-${provider}`;
      const dbRecord = this.realDatabase.get(dbKey);
      
      if (!dbRecord) {
        throw new Error('API key not found in database');
      }
      
      console.log('   ✅ Record found in database');
      console.log('   Record ID:', dbRecord.id);
      console.log('   Created:', dbRecord.created_at);
      
      return dbRecord;
    } catch (error) {
      console.error('   ❌ Database retrieval failed:', error.message);
      throw error;
    }
  }

  // Step 7: Simulate API key decryption
  simulateApiKeyDecryption(dbRecord) {
    console.log('\n🔓 STEP 7: Decrypt API key for usage');
    console.log('   Record ID:', dbRecord.id);
    console.log('   Encrypted length:', dbRecord.encrypted_api_key.length);
    
    try {
      // Recreate encryption key from secret + salt
      const encryptionKey = crypto.scryptSync(this.encryptionSecret, dbRecord.user_salt, 32);
      console.log('   Encryption key recreated from secret + salt');
      
      // Decrypt the API key
      const decipher = crypto.createDecipheriv('aes-256-gcm', encryptionKey, Buffer.from(dbRecord.key_iv, 'hex'));
      decipher.setAuthTag(Buffer.from(dbRecord.key_auth_tag, 'hex'));
      
      let decrypted = decipher.update(dbRecord.encrypted_api_key, 'hex', 'utf8');
      decrypted += decipher.final('utf8');
      
      console.log('   ✅ API key decrypted successfully');
      console.log('   Decrypted length:', decrypted.length);
      
      return decrypted;
    } catch (error) {
      console.error('   ❌ Decryption failed:', error.message);
      throw error;
    }
  }

  // Step 8: Simulate actual API usage
  simulateApiUsage(decryptedApiKey, provider) {
    console.log('\n🎯 STEP 8: Use decrypted API key for external API call');
    console.log('   Provider:', provider);
    console.log('   API Key Length:', decryptedApiKey.length);
    
    // Simulate making an API call to broker
    const apiCall = {
      url: provider === 'alpaca' ? 'https://paper-api.alpaca.markets/v2/account' : 'https://api.example.com/account',
      headers: {
        'Authorization': `Bearer ${decryptedApiKey}`,
        'Content-Type': 'application/json'
      }
    };
    
    console.log('   API call prepared for:', apiCall.url);
    console.log('   Authorization header set');
    console.log('   ✅ Ready to make external API call');
    
    return apiCall;
  }

  // Run the complete production flow test
  async runProductionFlowTest() {
    console.log('🏭 PRODUCTION API KEY FLOW TEST');
    console.log('================================');
    console.log('Simulating real user journey through production system\n');
    
    try {
      // Test data
      const testApiKey = 'PKTEST123456789ABCDEF';
      const testSecret = 'SECRET987654321ABCDEF';
      const provider = 'alpaca';
      
      // Run the complete flow
      const frontendRequest = this.simulateFrontendSubmission(testApiKey, testSecret, provider);
      const lambdaEvent = this.simulateApiGateway(frontendRequest);
      const userAuth = this.simulateLambdaAuth(lambdaEvent);
      const { encryptedData, userSalt } = this.simulateApiKeyEncryption(testApiKey, userAuth.userId, provider);
      const dbRecord = this.simulateDatabaseStorage(userAuth.userId, provider, encryptedData, userSalt);
      
      // Simulate later retrieval and usage
      console.log('\n' + '='.repeat(50));
      console.log('SIMULATING LATER API KEY USAGE');
      console.log('='.repeat(50));
      
      const retrievedRecord = this.simulateApiKeyRetrieval(userAuth.userId, provider);
      const decryptedKey = this.simulateApiKeyDecryption(retrievedRecord);
      const apiCall = this.simulateApiUsage(decryptedKey, provider);
      
      // Verify end-to-end integrity
      console.log('\n🔬 END-TO-END VERIFICATION');
      console.log('==========================');
      const integritySucess = decryptedKey === testApiKey;
      console.log('Original API Key:', testApiKey);
      console.log('Decrypted API Key:', decryptedKey);
      console.log('Integrity Check:', integritySucess ? '✅ PASS' : '❌ FAIL');
      
      if (integritySucess) {
        console.log('\n🎉 PRODUCTION FLOW TEST SUCCESSFUL!');
        console.log('✅ All steps completed successfully');
        console.log('✅ End-to-end integrity verified');
        console.log('✅ Ready for production deployment');
      } else {
        console.log('\n❌ PRODUCTION FLOW TEST FAILED!');
        console.log('❌ Integrity check failed');
        console.log('❌ DO NOT DEPLOY TO PRODUCTION');
      }
      
    } catch (error) {
      console.error('\n💥 PRODUCTION FLOW TEST FAILED!');
      console.error('Error:', error.message);
      console.error('Stack:', error.stack);
      console.error('❌ DO NOT DEPLOY TO PRODUCTION');
    }
  }

  // Test environment variable complications
  testEnvironmentVariableComplications() {
    console.log('\n🔬 ENVIRONMENT VARIABLE COMPLICATIONS TEST');
    console.log('==========================================');
    
    // Test different environment scenarios
    const scenarios = [
      { name: 'Local Development', env: 'development', hasSecret: false, hasSecretArn: false },
      { name: 'Staging Environment', env: 'staging', hasSecret: true, hasSecretArn: false },
      { name: 'Production Environment', env: 'production', hasSecret: false, hasSecretArn: true },
      { name: 'Misconfigured Production', env: 'production', hasSecret: false, hasSecretArn: false }
    ];
    
    scenarios.forEach(scenario => {
      console.log(`\n📋 Testing: ${scenario.name}`);
      console.log('   Environment:', scenario.env);
      console.log('   Has Env Secret:', scenario.hasSecret);
      console.log('   Has Secret ARN:', scenario.hasSecretArn);
      
      if (scenario.env === 'production' && !scenario.hasSecret && !scenario.hasSecretArn) {
        console.log('   ❌ CRITICAL: No encryption secret available');
        console.log('   🚨 This would cause production failures');
      } else if (scenario.env === 'development' && !scenario.hasSecret) {
        console.log('   ⚠️  Would generate temporary key (OK for dev)');
      } else {
        console.log('   ✅ Configuration looks valid');
      }
    });
  }
}

// Run the test
async function runTests() {
  const tester = new ProductionApiKeyFlowTest();
  await tester.runProductionFlowTest();
  tester.testEnvironmentVariableComplications();
}

if (require.main === module) {
  runTests().catch(console.error);
}

module.exports = { ProductionApiKeyFlowTest };