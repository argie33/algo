#!/usr/bin/env node

/**
 * Database Connection Setup Helper
 * 
 * This script helps configure direct database access to use real loadinfo data
 * instead of mock data in Stock Explorer.
 * 
 * Usage: node setup-database-connection.js
 */

const fs = require('fs');
const path = require('path');

console.log('🔧 Database Connection Setup Helper');
console.log('==================================');
console.log('');
console.log('This script will help you configure direct database access');
console.log('to use your real loadinfo data instead of mock data.');
console.log('');

// Check if .env.local exists
const envPath = path.join(__dirname, '.env.local');
let envContent = '';

if (fs.existsSync(envPath)) {
    envContent = fs.readFileSync(envPath, 'utf8');
    console.log('✅ Found existing .env.local file');
} else {
    console.log('ℹ️  Creating new .env.local file');
}

// Check current environment variables
const hasDirectDbVars = process.env.DB_HOST && process.env.DB_USER && process.env.DB_PASSWORD;
console.log('');
console.log('Current Database Configuration:');
console.log('==============================');
console.log(`NODE_ENV: ${process.env.NODE_ENV || 'not set'}`);
console.log(`DB_HOST: ${process.env.DB_HOST ? '✅ set' : '❌ not set'}`);
console.log(`DB_USER: ${process.env.DB_USER ? '✅ set' : '❌ not set'}`);
console.log(`DB_PASSWORD: ${process.env.DB_PASSWORD ? '✅ set' : '❌ not set'}`);
console.log(`DB_SECRET_ARN: ${process.env.DB_SECRET_ARN ? '✅ set' : '❌ not set'}`);
console.log('');

if (hasDirectDbVars && process.env.NODE_ENV === 'development') {
    console.log('✅ Direct database variables are configured correctly!');
    console.log('   Your Stock Explorer should now show real loadinfo data.');
    console.log('');
    console.log('🔄 Test your connection by running:');
    console.log('   node test-database-connection.js');
} else {
    console.log('❌ Direct database configuration incomplete.');
    console.log('');
    console.log('To fix this, you need to add these environment variables to .env.local:');
    console.log('');
    console.log('NODE_ENV=development');
    console.log('DB_HOST=your_database_host');
    console.log('DB_USER=your_database_username');
    console.log('DB_PASSWORD=your_database_password');
    console.log('DB_NAME=your_database_name  # optional, defaults to "stocks"');
    console.log('DB_PORT=5432  # optional, defaults to 5432');
    console.log('DB_SSL=false  # optional, defaults to false');
    console.log('');
    
    // Generate template .env.local content
    const templateEnv = `NODE_ENV=development
# Use AWS Secrets Manager for production database credentials
AWS_REGION=us-east-1
WEBAPP_AWS_REGION=us-east-1
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:3003

# Direct database connection (for development access to real loadinfo data)
# Replace these with your actual database credentials:
DB_HOST=your_database_host_here
DB_USER=your_database_username_here
DB_PASSWORD=your_database_password_here
DB_NAME=stocks
DB_PORT=5432
DB_SSL=false
`;

    console.log('📝 Template .env.local content:');
    console.log('==============================');
    console.log(templateEnv);
    
    console.log('🔍 Next steps:');
    console.log('1. Update .env.local with your actual database credentials');
    console.log('2. Make sure your database contains the loadinfo tables:');
    console.log('   - stock_symbols');
    console.log('   - symbols');
    console.log('   - market_data');
    console.log('   - key_metrics');
    console.log('   - analyst_estimates');
    console.log('   - governance_scores');
    console.log('3. Restart your API server');
    console.log('4. Test with: node test-database-connection.js');
}