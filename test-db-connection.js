#!/usr/bin/env node

const { Client } = require('pg');
const AWS = require('aws-sdk');

async function testConnection() {
  console.log('Testing direct database connection...');
  
  // Get credentials like Python scripts
  const secretsManager = new AWS.SecretsManager({ region: 'us-east-1' });
  const secretArn = 'arn:aws:secretsmanager:us-east-1:293337163605:secret:stocks-db-secrets-stocks-app-stack-us-east-1-001-5S5KUj';
  
  try {
    console.log('Retrieving secret...');
    const secret = await secretsManager.getSecretValue({ SecretId: secretArn }).promise();
    const credentials = JSON.parse(secret.SecretString);
    
    console.log('Credentials:', {
      host: credentials.host,
      port: credentials.port,
      database: credentials.dbname,
      user: credentials.username
    });
    
    // Test different SSL configurations
    const sslConfigs = [
      { name: 'No SSL', ssl: false },
      { name: 'SSL Basic', ssl: true },
      { name: 'SSL Reject Unauthorized False', ssl: { rejectUnauthorized: false } },
      { name: 'SSL Require', ssl: { mode: 'require' } }
    ];
    
    for (const config of sslConfigs) {
      console.log(`\n--- Testing ${config.name} ---`);
      
      const client = new Client({
        host: credentials.host,
        port: parseInt(credentials.port),
        database: credentials.dbname,
        user: credentials.username,
        password: credentials.password,
        ssl: config.ssl,
        connectionTimeoutMillis: 10000
      });
      
      try {
        const start = Date.now();
        await client.connect();
        const connectTime = Date.now() - start;
        console.log(`✅ ${config.name}: Connected in ${connectTime}ms`);
        
        const result = await client.query('SELECT NOW() as timestamp');
        console.log(`✅ Query successful:`, result.rows[0]);
        
        await client.end();
        console.log(`✅ ${config.name}: SUCCESS`);
        break; // Exit on first success
        
      } catch (error) {
        console.log(`❌ ${config.name}: ${error.message}`);
        try { await client.end(); } catch {}
      }
    }
    
  } catch (error) {
    console.error('Test failed:', error.message);
  }
}

testConnection().catch(console.error);
