#!/usr/bin/env node

// Direct database connection test using the exact same credentials as ECS and Lambda
const { Client } = require('pg');
const AWS = require('aws-sdk');

const secretsManager = new AWS.SecretsManager({ region: 'us-east-1' });

async function testDirectConnection() {
    console.log('🧪 Testing direct database connection...');
    
    try {
        // Get the exact same secret the ECS/Lambda would use
        const secretArn = 'arn:aws:secretsmanager:us-east-1:905418313413:secret:stocks-db-secrets-stocks-app-stack-us-east-1-001-fl3BxQ';
        
        console.log('📋 Getting database credentials from Secrets Manager...');
        const secretResponse = await secretsManager.getSecretValue({ SecretId: secretArn }).promise();
        const secret = JSON.parse(secretResponse.SecretString);
        
        console.log('🔧 Database config:');
        console.log(`   Host: ${secret.host}`);
        console.log(`   Port: ${secret.port}`);
        console.log(`   Database: ${secret.dbname}`);
        console.log(`   User: ${secret.username}`);
        
        // Test 1: Without SSL (ECS-like)
        console.log('\n🧪 Test 1: Connection WITHOUT SSL (ECS pattern)');
        const configNoSSL = {
            host: secret.host,
            port: parseInt(secret.port) || 5432,
            database: secret.dbname,
            user: secret.username,
            password: secret.password,
            ssl: false,
            connectionTimeoutMillis: 10000
        };
        
        const clientNoSSL = new Client(configNoSSL);
        try {
            await clientNoSSL.connect();
            console.log('✅ NO SSL connection: SUCCESS');
            
            const result = await clientNoSSL.query('SELECT NOW() as current_time, version() as db_version');
            console.log(`   Database time: ${result.rows[0].current_time}`);
            console.log(`   PostgreSQL version: ${result.rows[0].db_version.split(' ')[0]}`);
            
            await clientNoSSL.end();
        } catch (error) {
            console.log('❌ NO SSL connection: FAILED');
            console.log(`   Error: ${error.message}`);
            console.log(`   Code: ${error.code}`);
        }
        
        // Test 2: With SSL (Lambda pattern - old)
        console.log('\n🧪 Test 2: Connection WITH REQUIRED SSL (old Lambda pattern)');
        const configWithSSL = {
            host: secret.host,
            port: parseInt(secret.port) || 5432,
            database: secret.dbname,
            user: secret.username,
            password: secret.password,
            ssl: {
                rejectUnauthorized: false,
                require: true
            },
            connectionTimeoutMillis: 10000
        };
        
        const clientWithSSL = new Client(configWithSSL);
        try {
            await clientWithSSL.connect();
            console.log('✅ REQUIRED SSL connection: SUCCESS');
            
            const result = await clientWithSSL.query('SELECT NOW() as current_time');
            console.log(`   Database time: ${result.rows[0].current_time}`);
            
            await clientWithSSL.end();
        } catch (error) {
            console.log('❌ REQUIRED SSL connection: FAILED');
            console.log(`   Error: ${error.message}`);
            console.log(`   Code: ${error.code}`);
        }
        
        // Test 3: With SSL optional (new Lambda pattern)
        console.log('\n🧪 Test 3: Connection WITH OPTIONAL SSL (new Lambda pattern)');
        const configOptionalSSL = {
            host: secret.host,
            port: parseInt(secret.port) || 5432,
            database: secret.dbname,
            user: secret.username,
            password: secret.password,
            ssl: {
                rejectUnauthorized: false
                // No "require: true" - SSL optional
            },
            connectionTimeoutMillis: 10000
        };
        
        const clientOptionalSSL = new Client(configOptionalSSL);
        try {
            await clientOptionalSSL.connect();
            console.log('✅ OPTIONAL SSL connection: SUCCESS');
            
            const result = await clientOptionalSSL.query('SELECT NOW() as current_time');
            console.log(`   Database time: ${result.rows[0].current_time}`);
            
            await clientOptionalSSL.end();
        } catch (error) {
            console.log('❌ OPTIONAL SSL connection: FAILED');
            console.log(`   Error: ${error.message}`);
            console.log(`   Code: ${error.code}`);
        }
        
        console.log('\n📊 TEST SUMMARY:');
        console.log('   ECS pattern (no SSL): Working = ECS tasks succeed');
        console.log('   Lambda old (required SSL): Failing = Lambda fails');
        console.log('   Lambda new (optional SSL): Should work = Lambda should work');
        
    } catch (error) {
        console.error('❌ Test failed:', error.message);
        process.exit(1);
    }
}

// Run test
testDirectConnection().catch(console.error);