const { Pool } = require('pg');
const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');
const { Signer } = require('@aws-sdk/rds-signer');

let pool = null;

async function getDbCredentials() {
  const nodeEnv = process.env.NODE_ENV || 'production';
  const isLocalDev = nodeEnv === 'development' || nodeEnv === 'dev';
  
  console.log('Environment check:', {
    NODE_ENV: nodeEnv,
    isLocalDev,
    DB_ENDPOINT: process.env.DB_ENDPOINT,
    DB_SECRET_ARN: process.env.DB_SECRET_ARN ? 'SET' : 'NOT_SET',
    WEBAPP_AWS_REGION: process.env.WEBAPP_AWS_REGION
  });
  
  if (isLocalDev && !process.env.DB_SECRET_ARN) {
    // For local development - use local env vars
    console.log('Using local development database configuration...');
    return {
      host: process.env.DB_HOST || 'localhost',
      port: parseInt(process.env.DB_PORT) || 5432,
      database: process.env.DB_NAME || 'fundamentals',
      user: process.env.DB_USER || 'postgres',
      password: process.env.DB_PASSWORD || 'password',
      useIAM: false
    };
  }  
  // Check if we have DB_ENDPOINT but need to use Secrets Manager for credentials
  if (!process.env.DB_SECRET_ARN) {
    console.error('DB_SECRET_ARN not provided for production environment');
    throw new Error('Database configuration incomplete: DB_SECRET_ARN required for production');
  }
  
  // For production, use Secrets Manager (same as all Python scripts)
  console.log('Using AWS Secrets Manager for database credentials...');
  const client = new SecretsManagerClient({ 
    region: process.env.WEBAPP_AWS_REGION || 'us-east-1',
    maxAttempts: 3, // Allow 3 attempts for better reliability
    requestHandler: {
      requestTimeout: 30000, // Increase timeout to 30 seconds
      connectionTimeout: 10000 // Connection timeout of 10 seconds
    }
  });
  
  try {
    console.log('Retrieving secret from:', process.env.DB_SECRET_ARN);
    
    const command = new GetSecretValueCommand({
      SecretId: process.env.DB_SECRET_ARN
    });
    
    // Add timeout to secrets retrieval - give it more time
    const response = await Promise.race([
      client.send(command),
      new Promise((_, reject) => 
        setTimeout(() => reject(new Error('Secrets Manager timeout after 30 seconds')), 30000)
      )
    ]);
    
    console.log('Secret retrieved successfully, parsing...');
    const secret = JSON.parse(response.SecretString);
      console.log('Secret parsed, extracting database config...');
    return {
      host: secret.host || process.env.DB_ENDPOINT,
      port: parseInt(secret.port) || 5432,
      database: secret.dbname || secret.database || process.env.DB_NAME || 'stocks',
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
    });    // Create database pool with optimized settings
    const poolConfig = {
      host: credentials.host,
      port: credentials.port,
      database: credentials.database,
      user: credentials.user,
      password: credentials.password,
      // Performance optimizations based on Lambda environment
      max: parseInt(process.env.DB_POOL_MAX) || 5, // Max connections
      min: 1, // Keep minimum connections alive
      idleTimeoutMillis: parseInt(process.env.DB_POOL_IDLE_TIMEOUT) || 30000,
      connectionTimeoutMillis: parseInt(process.env.DB_CONNECT_TIMEOUT) || 10000,
      acquireTimeoutMillis: 8000, // Time to wait for connection from pool
      createTimeoutMillis: 8000, // Time to wait for new connection creation
      destroyTimeoutMillis: 5000, // Time to wait for connection destruction
      reapIntervalMillis: 1000, // How often to check for idle connections
      createRetryIntervalMillis: 200, // Retry interval for connection creation
      ssl: { rejectUnauthorized: false }, // AWS RDS requires SSL
      // Additional PostgreSQL specific optimizations
      statement_timeout: 25000, // 25 second query timeout
      query_timeout: 25000,
      application_name: `financial-dashboard-${process.env.NODE_ENV || 'production'}`,
      // Connection keep-alive
      keepAlive: true,
      keepAliveInitialDelayMillis: 10000,
    };

    pool = new Pool(poolConfig);
    
    console.log('Database pool created, testing connection...');
    
    // Test the connection
    let client;
    try {
      console.log('Starting database connection attempt...');
      const connectStart = Date.now();
      
      client = await Promise.race([
        pool.connect(),
        new Promise((_, reject) => 
          setTimeout(() => reject(new Error('Database connection timeout after 10 seconds')), 10000)
        )
      ]);
      
      const connectTime = Date.now() - connectStart;
      console.log(`Database client connected successfully in ${connectTime}ms`);
      
      // Simple test query
      const queryStart = Date.now();
      const result = await client.query('SELECT 1 as test');
      const queryTime = Date.now() - queryStart;
      console.log(`Database test query successful in ${queryTime}ms:`, result.rows[0]);
      
    } catch (connectionError) {
      console.error('Database connection failed:', connectionError.message);
      throw connectionError;
    } finally {
      if (client) {
        client.release();
      }
    }
    
    console.log('Database connection pool initialized successfully');
    return pool;  } catch (error) {
    console.error('Database initialization failed:', error.message);
    
    // Clean up failed pool
    if (pool) {
      try {
        await pool.end();
        pool = null;
      } catch (cleanupError) {
        console.error('Error cleaning up failed pool:', cleanupError.message);
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
