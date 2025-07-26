// Simple database connectivity test for Lambda
const { Pool } = require('pg');
const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');

async function testDatabaseConnectivity() {
  console.log('🔍 Testing Lambda database connectivity...');
  
  try {
    // Step 1: Test Secrets Manager access
    console.log('1️⃣ Testing AWS Secrets Manager access...');
    const secretsManager = new SecretsManagerClient({
      region: process.env.WEBAPP_AWS_REGION || 'us-east-1'
    });
    
    const secretArn = process.env.DB_SECRET_ARN;
    if (!secretArn) {
      throw new Error('DB_SECRET_ARN not set');
    }
    
    const command = new GetSecretValueCommand({ SecretId: secretArn });
    const secretResponse = await secretsManager.send(command);
    const dbSecret = JSON.parse(secretResponse.SecretString);
    
    console.log('✅ Secrets Manager access successful');
    console.log(`   Host: ${dbSecret.host}:${dbSecret.port}`);
    console.log(`   Database: ${dbSecret.database}`);
    console.log(`   Username: ${dbSecret.username}`);
    
    // Step 2: Test basic network connectivity
    console.log('2️⃣ Testing database connection...');
    
    const config = {
      host: dbSecret.host,
      port: dbSecret.port,
      database: dbSecret.database,
      user: dbSecret.username,
      password: dbSecret.password,
      connectionTimeoutMillis: 10000,
      query_timeout: 5000,
      ssl: { rejectUnauthorized: false }
    };
    
    const pool = new Pool(config);
    
    // Step 3: Test simple query
    console.log('3️⃣ Testing simple query...');
    const start = Date.now();
    const result = await pool.query('SELECT 1 as test, now() as timestamp');
    const duration = Date.now() - start;
    
    console.log('✅ Database query successful');
    console.log(`   Query result: ${JSON.stringify(result.rows[0])}`);
    console.log(`   Duration: ${duration}ms`);
    
    // Step 4: Test table existence
    console.log('4️⃣ Testing table structure...');
    const tablesResult = await pool.query(`
      SELECT table_name 
      FROM information_schema.tables 
      WHERE table_schema = 'public' 
      ORDER BY table_name
    `);
    
    console.log('✅ Tables found:', tablesResult.rows.map(r => r.table_name));
    
    await pool.end();
    
    return {
      success: true,
      message: 'Database connectivity test passed',
      details: {
        secretsManager: true,
        connection: true,
        query: true,
        duration: duration,
        tables: tablesResult.rows.length
      }
    };
    
  } catch (error) {
    console.error('❌ Database connectivity test failed:', error.message);
    console.error('   Error details:', error);
    
    return {
      success: false,
      error: error.message,
      errorCode: error.code,
      errorDetails: error.detail
    };
  }
}

// Export for Lambda use
module.exports.handler = async (event, context) => {
  const result = await testDatabaseConnectivity();
  
  return {
    statusCode: 200,
    headers: {
      'Content-Type': 'application/json',
      'Access-Control-Allow-Origin': '*'
    },
    body: JSON.stringify(result, null, 2)
  };
};

// For local testing
if (require.main === module) {
  testDatabaseConnectivity().then(result => {
    console.log('🏁 Test completed:', JSON.stringify(result, null, 2));
    process.exit(result.success ? 0 : 1);
  });
}