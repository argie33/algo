const { Pool } = require('pg');
const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');
const { Signer } = require('@aws-sdk/rds-signer');

let pool = null;

async function getDbCredentials() {
  if (process.env.NODE_ENV === 'development') {
    // For local development
    return {
      host: process.env.DB_HOST || 'localhost',
      port: parseInt(process.env.DB_PORT) || 5432,
      database: process.env.DB_NAME || 'stocks',
      user: process.env.DB_USER || 'postgres',
      password: process.env.DB_PASSWORD || 'password',
      useIAM: false
    };
  }
  
  // For production, check if we should use IAM auth or secrets
  if (process.env.USE_IAM_DB_AUTH === 'true') {
    // Use IAM database authentication
    const signer = new Signer({
      region: process.env.WEBAPP_AWS_REGION || 'us-east-1',
      hostname: process.env.DB_ENDPOINT,
      port: 5432,
      username: process.env.IAM_DB_USER || 'lambda_user'
    });
    
    const token = await signer.getAuthToken();
    
    return {
      host: process.env.DB_ENDPOINT,
      port: 5432,
      database: 'stocks',
      user: process.env.IAM_DB_USER || 'lambda_user',
      password: token,
      useIAM: true
    };
  }
  
  // Fall back to Secrets Manager
  const client = new SecretsManagerClient({ 
    region: process.env.WEBAPP_AWS_REGION || 'us-east-1' 
  });
  
  try {
    const command = new GetSecretValueCommand({
      SecretId: process.env.DB_SECRET_ARN
    });
    
    const response = await client.send(command);
    const secret = JSON.parse(response.SecretString);
      return {
      host: secret.host || process.env.DB_ENDPOINT,
      port: parseInt(secret.port) || 5432,
      database: secret.dbname || 'stocks', // Match Python code: uses 'dbname' field
      user: secret.username,
      password: secret.password,
      useIAM: false
    };
  } catch (error) {
    console.error('Error retrieving database credentials:', error);
    throw error;
  }
}

async function initializeDatabase() {
  try {
    console.log('Starting database initialization...');
    
    // Add debugging for environment variables
    console.log('Environment check:', {
      NODE_ENV: process.env.NODE_ENV,
      DB_ENDPOINT: process.env.DB_ENDPOINT,
      DB_SECRET_ARN: process.env.DB_SECRET_ARN ? 'SET' : 'NOT_SET',
      WEBAPP_AWS_REGION: process.env.WEBAPP_AWS_REGION
    });
    
    const credentials = await getDbCredentials();
    console.log('Database credentials retrieved:', {
      host: credentials.host,
      port: credentials.port,
      database: credentials.database,
      user: credentials.user,
      useIAM: credentials.useIAM
      // Don't log password
    });
      // Match the working Python psycopg2 connection pattern
    pool = new Pool({
      host: credentials.host,
      port: credentials.port,
      database: credentials.database,
      user: credentials.user,
      password: credentials.password,
      max: 3, // Reduced for Lambda
      idleTimeoutMillis: 30000,
      connectionTimeoutMillis: 10000, // Match working timeout
      // Simplified SSL - match Python defaults
      ssl: process.env.NODE_ENV === 'production' ? true : false
    });    console.log('Database pool created, testing connection...');
      // Test the connection with detailed error logging
    let client;
    try {
      console.log('Attempting to connect to database with config:', {
        host: credentials.host,
        port: credentials.port,
        database: credentials.database,
        user: credentials.user,
        ssl: process.env.NODE_ENV === 'production' ? true : false
      });
      
      console.log('Starting database connection attempt...');
      const connectStart = Date.now();
      
      client = await Promise.race([
        pool.connect(),
        new Promise((_, reject) => 
          setTimeout(() => reject(new Error('Database connection timeout after 8 seconds')), 8000)
        )
      ]);
      
      const connectTime = Date.now() - connectStart;
      console.log(`Database client connected successfully in ${connectTime}ms`);
      
      // Simple test query like Python code
      console.log('Testing database query...');
      const queryStart = Date.now();
      const result = await client.query('SELECT 1 as test');
      const queryTime = Date.now() - queryStart;
      console.log(`Database test query successful in ${queryTime}ms:`, result.rows[0]);
      client.release();
      
    } catch (connectionError) {
      console.error('Database connection failed with detailed error:', {
        message: connectionError.message,
        code: connectionError.code,
        errno: connectionError.errno,
        syscall: connectionError.syscall,
        address: connectionError.address,
        port: connectionError.port,
        host: connectionError.host,
        stack: connectionError.stack
      });
      
      // Also log pool status
      console.error('Pool status:', {
        totalCount: pool.totalCount,
        idleCount: pool.idleCount,
        waitingCount: pool.waitingCount
      });
      
      throw connectionError;
    }
    
    console.log('Database connection pool initialized successfully');
    return pool;
  } catch (error) {
    console.error('Failed to initialize database connection:', {
      message: error.message,
      code: error.code,
      stack: error.stack,
      timeout: error.timeout
    });
    
    // Clean up failed pool
    if (pool) {
      try {
        await pool.end();
        pool = null;
      } catch (cleanupError) {
        console.error('Error cleaning up failed pool:', cleanupError);
      }
    }
    
    throw error;
  }
}

function getPool() {
  if (!pool) {
    throw new Error('Database not initialized. Call initializeDatabase() first.');
  }
  return pool;
}

async function query(text, params) {
  const client = await getPool().connect();
  try {
    const result = await client.query(text, params);
    return result;
  } catch (error) {
    console.error('Database query error:', error);
    throw error;
  } finally {
    client.release();
  }
}

async function getClient() {
  return await getPool().connect();
}

module.exports = {
  initializeDatabase,
  getPool,
  query,
  getClient
};
