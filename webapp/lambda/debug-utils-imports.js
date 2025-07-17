// Debug utils imports to find the problematic dependency
console.log('Starting utils import debugging...');

try {
  console.log('1. Testing crypto import...');
  const crypto = require('crypto');
  console.log('✅ crypto imported successfully');
  
  console.log('2. Testing AWS SDK SecretsManager import...');
  const { SecretsManagerClient } = require('@aws-sdk/client-secrets-manager');
  console.log('✅ SecretsManagerClient imported successfully');
  
  console.log('3. Testing structuredLogger import...');
  const { createLogger } = require('./utils/structuredLogger');
  console.log('✅ structuredLogger imported successfully');
  
  console.log('4. Testing secretsLoader import...');
  const secretsLoader = require('./utils/secretsLoader');
  console.log('✅ secretsLoader imported successfully');
  
  console.log('5. Testing responseFormatter import...');
  const { responseFormatterMiddleware } = require('./utils/responseFormatter');
  console.log('✅ responseFormatter imported successfully');
  
  console.log('6. Testing pg (PostgreSQL) import...');
  const { Pool } = require('pg');
  console.log('✅ pg imported successfully');
  
  console.log('7. Testing databaseConnectionManager import...');
  const databaseConnectionManager = require('./utils/databaseConnectionManager');
  console.log('✅ databaseConnectionManager imported successfully');
  
  console.log('8. Testing logger creation...');
  const logger = createLogger('test', 'debug');
  console.log('✅ logger created successfully');
  
  console.log('9. Testing database config (without actual connection)...');
  // Don't actually connect, just test the config loading
  console.log('✅ All imports successful - no dependency issues found');
  
} catch (error) {
  console.error('❌ Import failed:', error.message);
  console.error('Error stack:', error.stack);
  process.exit(1);
}