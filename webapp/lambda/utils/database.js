const { Pool } = require('pg');
const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');

let pool = null;

async function getDbCredentials() {
  if (process.env.NODE_ENV === 'development') {
    // For local development
    return {
      host: process.env.DB_HOST || 'localhost',
      port: parseInt(process.env.DB_PORT) || 5432,
      database: process.env.DB_NAME || 'stocks',
      user: process.env.DB_USER || 'postgres',
      password: process.env.DB_PASSWORD || 'password'
    };
  }
  // For production, get credentials from AWS Secrets Manager
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
      host: secret.host,
      port: parseInt(secret.port),
      database: secret.dbname,
      user: secret.username,
      password: secret.password
    };
  } catch (error) {
    console.error('Error retrieving database credentials:', error);
    throw error;
  }
}

async function initializeDatabase() {
  try {
    console.log('Starting database initialization...');
    const credentials = await getDbCredentials();
    console.log('Database credentials retrieved:', {
      host: credentials.host,
      port: credentials.port,
      database: credentials.database,
      user: credentials.user
      // Don't log password
    });
      pool = new Pool({
      ...credentials,
      max: 3, // Reduced for Lambda
      idleTimeoutMillis: 20000,
      connectionTimeoutMillis: 5000, // Reduced timeout for faster failures
      statement_timeout: 15000, // Query timeout
      query_timeout: 15000,
      acquireTimeoutMillis: 5000, // How long to wait for a connection
      ssl: process.env.NODE_ENV === 'production' ? { 
        rejectUnauthorized: false,
        sslmode: 'require'
      } : false
    });

    console.log('Database pool created, testing connection...');
    
    // Test the connection with shorter timeout
    const client = await Promise.race([
      pool.connect(),
      new Promise((_, reject) => 
        setTimeout(() => reject(new Error('Database connection timeout')), 4000)
      )
    ]);
    
    console.log('Database client connected, testing query...');
    const result = await client.query('SELECT NOW() as current_time, version() as db_version');
    console.log('Database test query successful:', result.rows[0]);
    client.release();
    
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
