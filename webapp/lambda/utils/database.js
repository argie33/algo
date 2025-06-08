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
    const credentials = await getDbCredentials();
    
    pool = new Pool({
      ...credentials,
      max: 10,
      idleTimeoutMillis: 30000,
      connectionTimeoutMillis: 2000,
      ssl: process.env.NODE_ENV === 'production' ? { rejectUnauthorized: false } : false
    });

    // Test the connection
    const client = await pool.connect();
    await client.query('SELECT NOW()');
    client.release();
    
    console.log('Database connection pool initialized successfully');
    return pool;
  } catch (error) {
    console.error('Failed to initialize database connection:', error);
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
