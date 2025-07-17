#!/usr/bin/env node

/**
 * Debug script to diagnose database connection issues
 * This script will help identify the root cause of the JSON parsing error
 */

const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');

async function debugDatabaseConnection() {
  console.log('🔍 Database Connection Debug Tool');
  console.log('=====================================');
  
  // Check environment variables
  console.log('\n1. Environment Variables Check:');
  console.log('NODE_ENV:', process.env.NODE_ENV);
  console.log('AWS_REGION:', process.env.AWS_REGION);
  console.log('WEBAPP_AWS_REGION:', process.env.WEBAPP_AWS_REGION);
  console.log('DB_SECRET_ARN:', process.env.DB_SECRET_ARN ? 'SET' : 'NOT SET');
  console.log('DB_ENDPOINT:', process.env.DB_ENDPOINT ? 'SET' : 'NOT SET');
  
  if (!process.env.DB_SECRET_ARN) {
    console.log('❌ DB_SECRET_ARN is not set - this is required for database connection');
    return;
  }
  
  const secretArn = process.env.DB_SECRET_ARN;
  console.log('Secret ARN:', secretArn);
  
  // Test AWS Secrets Manager connection
  console.log('\n2. AWS Secrets Manager Test:');
  const region = process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || 'us-east-1';
  console.log('Using region:', region);
  
  const secretsManager = new SecretsManagerClient({ region });
  
  try {
    console.log('📡 Calling GetSecretValue...');
    const command = new GetSecretValueCommand({ SecretId: secretArn });
    const response = await secretsManager.send(command);
    
    console.log('✅ Secrets Manager response received');
    console.log('Response keys:', Object.keys(response));
    console.log('SecretString exists:', !!response.SecretString);
    console.log('SecretString type:', typeof response.SecretString);
    
    if (response.SecretString) {
      console.log('Raw SecretString (first 50 chars):', response.SecretString.substring(0, 50));
      console.log('SecretString length:', response.SecretString.length);
      
      // Try to parse JSON
      console.log('\n3. JSON Parsing Test:');
      try {
        const parsed = JSON.parse(response.SecretString);
        console.log('✅ JSON parsing successful');
        console.log('Parsed object keys:', Object.keys(parsed));
        console.log('Has required fields:', {
          host: !!parsed.host,
          port: !!parsed.port,
          dbname: !!parsed.dbname,
          username: !!parsed.username,
          password: !!parsed.password
        });
      } catch (parseError) {
        console.error('❌ JSON parsing failed:', parseError.message);
        console.error('Parse error details:', parseError);
        
        // Try to identify the character causing the issue
        console.log('\n4. Character Analysis:');
        const str = response.SecretString;
        console.log('First 10 characters:', str.substring(0, 10).split('').map(c => `'${c}' (${c.charCodeAt(0)})`));
        console.log('Last 10 characters:', str.substring(str.length - 10).split('').map(c => `'${c}' (${c.charCodeAt(0)})`));
        
        // Check for common JSON issues
        if (str.includes('\\n')) {
          console.log('⚠️ Contains escaped newlines');
        }
        if (str.includes('\\t')) {
          console.log('⚠️ Contains escaped tabs');
        }
        if (str.includes('\\"')) {
          console.log('⚠️ Contains escaped quotes');
        }
      }
    }
    
  } catch (error) {
    console.error('❌ Secrets Manager call failed:', error.message);
    console.error('Error code:', error.name);
    console.error('Error details:', error);
  }
}

// Run the debug
debugDatabaseConnection().catch(console.error);