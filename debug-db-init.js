#!/usr/bin/env node
/**
 * Debug script for webapp database initialization
 * This script helps diagnose issues with the database initialization
 */

console.log('🔍 Starting database initialization debug...');
console.log('🔍 Environment Variables:');
console.log('  - DB_SECRET_ARN:', process.env.DB_SECRET_ARN ? 'SET' : 'NOT SET');
console.log('  - AWS_REGION:', process.env.AWS_REGION || 'NOT SET');
console.log('  - ENVIRONMENT:', process.env.ENVIRONMENT || 'NOT SET');

console.log('\n🔍 Checking required modules...');

// Check if required modules are available
const requiredModules = [
    'pg',
    '@aws-sdk/client-secrets-manager'
];

const missingModules = [];
for (const module of requiredModules) {
    try {
        require(module);
        console.log(`  ✅ ${module} - OK`);
    } catch (error) {
        console.log(`  ❌ ${module} - MISSING`);
        missingModules.push(module);
    }
}

if (missingModules.length > 0) {
    console.log('\n❌ Missing required modules:', missingModules.join(', '));
    console.log('💡 Run: npm install', missingModules.join(' '));
    process.exit(1);
}

console.log('\n🔍 Testing database connection...');

async function testDbConnection() {
    try {
        const { Client } = require('pg');
        const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');
        
        console.log('  🔧 Initializing AWS SDK...');
        const secretsManager = new SecretsManagerClient({
            region: process.env.AWS_REGION || 'us-east-1'
        });
        
        console.log('  🔧 Fetching database credentials...');
        const secretArn = process.env.DB_SECRET_ARN;
        if (!secretArn) {
            throw new Error('DB_SECRET_ARN environment variable not set');
        }
        
        const command = new GetSecretValueCommand({ SecretId: secretArn });
        const response = await secretsManager.send(command);
        const secret = JSON.parse(response.SecretString);
        
        console.log('  ✅ Database credentials fetched successfully');
        console.log('  🔧 Testing database connection...');
        
        const dbConfig = {
            host: secret.host,
            port: parseInt(secret.port) || 5432,
            database: secret.dbname || 'postgres',
            user: secret.username,
            password: secret.password,
            ssl: {
                require: true,
                rejectUnauthorized: false
            },
            connectionTimeoutMillis: 30000
        };
        
        const client = new Client(dbConfig);
        await client.connect();
        
        console.log('  ✅ Database connection successful');
        
        const result = await client.query('SELECT current_database() as db_name, current_user as db_user, version() as db_version');
        console.log('  📊 Database info:', result.rows[0]);
        
        await client.end();
        console.log('  ✅ Database connection closed');
        
        console.log('\n🎉 All checks passed! Database initialization should work.');
        return 0;
        
    } catch (error) {
        console.error('\n❌ Database connection test failed:', error.message);
        console.error('Full error:', error);
        return 1;
    }
}

testDbConnection().then(exitCode => {
    process.exit(exitCode);
}).catch(error => {
    console.error('Unhandled error:', error);
    process.exit(1);
});