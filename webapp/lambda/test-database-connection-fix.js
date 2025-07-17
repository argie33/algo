#!/usr/bin/env node

/**
 * Database Connection Diagnostic Script
 * Systematically tests database connection with different configurations
 * to identify the root cause of JSON parsing errors
 */

const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');
const { Pool } = require('pg');

// Configure AWS SDK
const secretsManager = new SecretsManagerClient({
    region: process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || 'us-east-1'
});

console.log('🔍 Starting systematic database connection diagnostics...');
console.log('📋 Environment Check:');
console.log(`   AWS_REGION: ${process.env.AWS_REGION || 'NOT_SET'}`);
console.log(`   WEBAPP_AWS_REGION: ${process.env.WEBAPP_AWS_REGION || 'NOT_SET'}`);
console.log(`   DB_SECRET_ARN: ${process.env.DB_SECRET_ARN ? 'SET' : 'NOT_SET'}`);
console.log(`   DB_ENDPOINT: ${process.env.DB_ENDPOINT ? 'SET' : 'NOT_SET'}`);
console.log('');

async function testSecretsManager() {
    console.log('🔐 Testing AWS Secrets Manager...');
    
    const secretArn = process.env.DB_SECRET_ARN;
    if (!secretArn) {
        console.error('❌ DB_SECRET_ARN environment variable not set');
        return null;
    }
    
    try {
        console.log(`📡 Fetching secret: ${secretArn}`);
        const command = new GetSecretValueCommand({ SecretId: secretArn });
        const response = await secretsManager.send(command);
        
        console.log('✅ Secrets Manager response received');
        console.log(`📊 Response metadata:`);
        console.log(`   SecretString length: ${response.SecretString ? response.SecretString.length : 'null'}`);
        console.log(`   SecretBinary: ${response.SecretBinary ? 'present' : 'null'}`);
        console.log(`   VersionId: ${response.VersionId || 'null'}`);
        
        // Debug the raw secret string
        console.log('🔍 Raw secret string analysis:');
        const secretString = response.SecretString;
        if (secretString) {
            console.log(`   First 50 characters: "${secretString.substring(0, 50)}"`);
            console.log(`   Last 50 characters: "${secretString.substring(secretString.length - 50)}"`);
            console.log(`   Starts with '{': ${secretString.startsWith('{')}`);
            console.log(`   Ends with '}': ${secretString.endsWith('}')}`);
            console.log(`   Contains 'host': ${secretString.includes('host')}`);
            console.log(`   Contains 'password': ${secretString.includes('password')}`);
        }
        
        // Test JSON parsing
        console.log('🧪 Testing JSON parsing...');
        try {
            const secret = JSON.parse(secretString);
            console.log('✅ JSON parsing successful');
            console.log(`📋 Secret structure:`);
            console.log(`   Keys: ${Object.keys(secret).join(', ')}`);
            console.log(`   Host: ${secret.host ? 'present' : 'missing'}`);
            console.log(`   Username: ${secret.username ? 'present' : 'missing'}`);
            console.log(`   Password: ${secret.password ? 'present' : 'missing'}`);
            console.log(`   Port: ${secret.port || 'missing'}`);
            console.log(`   Database: ${secret.dbname || 'missing'}`);
            
            return secret;
        } catch (parseError) {
            console.error('❌ JSON parsing failed:', parseError.message);
            console.error('❌ This is the root cause of the "Unexpected token o in JSON at position 1" error');
            
            // Try to identify the issue
            if (secretString.startsWith('o')) {
                console.error('🔍 Secret starts with "o" - this suggests a malformed secret');
            }
            
            return null;
        }
    } catch (error) {
        console.error('❌ Failed to fetch secret:', error.message);
        return null;
    }
}

async function testDatabaseConnection(secret) {
    if (!secret) {
        console.log('⏭️ Skipping database connection test - no valid secret');
        return;
    }
    
    console.log('\n🔌 Testing database connection...');
    
    // Test SSL-free configuration (matching working ECS tasks)
    const config = {
        host: secret.host || process.env.DB_ENDPOINT,
        port: parseInt(secret.port) || 5432,
        database: secret.dbname || 'stocks',
        user: secret.username,
        password: secret.password,
        ssl: false, // SSL-free configuration
        max: 1,
        idleTimeoutMillis: 5000,
        connectionTimeoutMillis: 10000
    };
    
    console.log('⚙️ Connection configuration:');
    console.log(`   Host: ${config.host}`);
    console.log(`   Port: ${config.port}`);
    console.log(`   Database: ${config.database}`);
    console.log(`   User: ${config.user}`);
    console.log(`   SSL: ${config.ssl}`);
    
    const pool = new Pool(config);
    
    try {
        console.log('📡 Attempting database connection...');
        const client = await pool.connect();
        console.log('✅ Database connection successful!');
        
        // Test basic query
        const result = await client.query('SELECT NOW() as current_time, version() as version');
        console.log('✅ Basic query successful:');
        console.log(`   Current time: ${result.rows[0].current_time}`);
        console.log(`   Version: ${result.rows[0].version}`);
        
        client.release();
        
    } catch (error) {
        console.error('❌ Database connection failed:', error.message);
        console.error('❌ Error code:', error.code);
        
        // Analyze the error
        if (error.message.includes('SSL')) {
            console.error('🔍 SSL-related error detected');
        }
        if (error.message.includes('timeout')) {
            console.error('🔍 Timeout error detected');
        }
        if (error.message.includes('authentication')) {
            console.error('🔍 Authentication error detected');
        }
        
    } finally {
        await pool.end();
    }
}

async function testCircuitBreakerStatus() {
    console.log('\n🔄 Testing circuit breaker status...');
    
    try {
        // Import the timeout helper to check circuit breaker status
        const timeoutHelper = require('./utils/timeoutHelper');
        const circuitBreakers = timeoutHelper.getCircuitBreakerStatus();
        
        console.log('📊 Circuit breaker status:');
        if (Object.keys(circuitBreakers).length === 0) {
            console.log('   No circuit breakers active');
        } else {
            for (const [serviceKey, breaker] of Object.entries(circuitBreakers)) {
                console.log(`   ${serviceKey}:`);
                console.log(`     State: ${breaker.state}`);
                console.log(`     Failures: ${breaker.failures}`);
                console.log(`     Time since last failure: ${Date.now() - breaker.lastFailureTime}ms`);
                
                if (breaker.state === 'open') {
                    const timeRemaining = Math.max(0, breaker.timeout - (Date.now() - breaker.lastFailureTime));
                    console.log(`     ⏰ Time until half-open: ${Math.ceil(timeRemaining / 1000)}s`);
                }
            }
        }
        
    } catch (error) {
        console.error('❌ Failed to check circuit breaker status:', error.message);
    }
}

async function main() {
    try {
        const secret = await testSecretsManager();
        await testDatabaseConnection(secret);
        await testCircuitBreakerStatus();
        
        console.log('\n🎯 DIAGNOSIS COMPLETE');
        console.log('=' .repeat(50));
        
        if (!secret) {
            console.log('❌ ROOT CAUSE: AWS Secrets Manager JSON parsing error');
            console.log('🔧 SOLUTION: Fix the secret format in AWS Secrets Manager');
            console.log('📋 NEXT STEPS:');
            console.log('   1. Check AWS Secrets Manager console');
            console.log('   2. Verify secret is valid JSON format');
            console.log('   3. Ensure secret contains required fields: host, username, password, port, dbname');
        } else {
            console.log('✅ SECRET PARSING: Working correctly');
            console.log('🔧 SOLUTION: Database connection configuration issue');
            console.log('📋 NEXT STEPS:');
            console.log('   1. Verify database endpoint is accessible');
            console.log('   2. Check security group settings');
            console.log('   3. Ensure SSL configuration matches working ECS tasks');
        }
        
    } catch (error) {
        console.error('❌ Diagnostic script failed:', error.message);
        console.error('❌ Stack trace:', error.stack);
    }
}

main();