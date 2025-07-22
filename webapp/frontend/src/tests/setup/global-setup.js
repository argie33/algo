/**
 * Global Setup for Integration Tests
 * Runs before all tests to set up the testing environment
 */

export default async function globalSetup() {
  console.log('🚀 Starting global setup for integration tests...');
  
  // Environment validation
  const requiredEnvVars = [
    'E2E_BASE_URL',
    'E2E_API_URL',
    'E2E_TEST_EMAIL',
    'E2E_TEST_PASSWORD'
  ];
  
  const missingVars = requiredEnvVars.filter(varName => !process.env[varName]);
  
  if (missingVars.length > 0) {
    console.log('⚠️ Missing environment variables:', missingVars);
    console.log('🔧 Using default values for missing variables...');
  } else {
    console.log('✅ All required environment variables are set');
  }
  
  // Set default values for missing environment variables
  if (!process.env.E2E_BASE_URL) {
    process.env.E2E_BASE_URL = 'https://d1zb7knau41vl9.cloudfront.net';
  }
  
  if (!process.env.E2E_API_URL) {
    process.env.E2E_API_URL = 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev';
  }
  
  if (!process.env.E2E_TEST_EMAIL) {
    process.env.E2E_TEST_EMAIL = 'e2e-test@example.com';
  }
  
  if (!process.env.E2E_TEST_PASSWORD) {
    process.env.E2E_TEST_PASSWORD = 'E2ETest123!';
  }
  
  console.log('🌐 Base URL:', process.env.E2E_BASE_URL);
  console.log('📡 API URL:', process.env.E2E_API_URL);
  console.log('👤 Test User:', process.env.E2E_TEST_EMAIL);
  
  // Create test results directory
  const fs = await import('fs');
  const path = await import('path');
  
  const testResultsDir = path.join(process.cwd(), 'test-results');
  if (!fs.existsSync(testResultsDir)) {
    fs.mkdirSync(testResultsDir, { recursive: true });
    console.log('📁 Created test results directory');
  }
  
  // Create artifacts directory
  const artifactsDir = path.join(testResultsDir, 'artifacts');
  if (!fs.existsSync(artifactsDir)) {
    fs.mkdirSync(artifactsDir, { recursive: true });
    console.log('📁 Created artifacts directory');
  }
  
  console.log('✅ Global setup completed');
}