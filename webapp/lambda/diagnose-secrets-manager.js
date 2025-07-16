#!/usr/bin/env node
/**
 * Secrets Manager Diagnostic Script
 * Identifies what's wrong with database secret retrieval
 */

const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');

// Configure AWS SDK for Secrets Manager
const secretsManager = new SecretsManagerClient({
    region: process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || 'us-east-1'
});

async function diagnoseSecretsManager() {
    console.log('🔍 Secrets Manager Diagnostic');
    console.log('='.repeat(40));
    
    try {
        // Check environment variables
        console.log('1. Environment Variables Check:');
        const dbSecretArn = process.env.DB_SECRET_ARN;
        console.log(`   DB_SECRET_ARN: ${dbSecretArn || 'NOT SET'}`);
        console.log(`   AWS_REGION: ${process.env.AWS_REGION || 'NOT SET'}`);
        console.log(`   WEBAPP_AWS_REGION: ${process.env.WEBAPP_AWS_REGION || 'NOT SET'}`);
        
        if (!dbSecretArn) {
            console.log('❌ DB_SECRET_ARN environment variable not set');
            console.log('   This is required for database configuration');
            return false;
        }
        
        console.log('\n2. Secrets Manager Access Test:');
        console.log(`   Attempting to retrieve: ${dbSecretArn}`);
        
        const command = new GetSecretValueCommand({ SecretId: dbSecretArn });
        const response = await secretsManager.send(command);
        
        console.log('✅ Secrets Manager responded successfully');
        console.log(`   SecretString type: ${typeof response.SecretString}`);
        console.log(`   SecretString length: ${response.SecretString ? response.SecretString.length : 'null'}`);
        console.log(`   SecretString first 50 chars: "${response.SecretString ? response.SecretString.substring(0, 50) : 'null'}"`);
        
        // Try to parse as JSON
        console.log('\n3. JSON Parsing Test:');
        try {
            const secret = JSON.parse(response.SecretString);
            console.log('✅ JSON parsing successful');
            console.log(`   Secret keys: ${Object.keys(secret).join(', ')}`);
            
            // Check required fields
            const requiredFields = ['host', 'port', 'dbname', 'username', 'password'];
            const missingFields = [];
            const presentFields = [];
            
            for (const field of requiredFields) {
                if (field in secret) {
                    presentFields.push(field);
                } else {
                    missingFields.push(field);
                }
            }
            
            console.log(`   ✅ Present fields: ${presentFields.join(', ')}`);
            if (missingFields.length > 0) {
                console.log(`   ❌ Missing fields: ${missingFields.join(', ')}`);
            }
            
            return missingFields.length === 0;
            
        } catch (parseError) {
            console.log('❌ JSON parsing failed');
            console.log(`   Error: ${parseError.message}`);
            console.log(`   This explains the "Unexpected token o in JSON at position 1" error`);
            
            // Show the problematic string
            console.log('\n   Raw SecretString content:');
            console.log(`   "${response.SecretString}"`);
            
            // Check if it's a different format
            if (response.SecretString.startsWith('arn:') || response.SecretString.includes('rds')) {
                console.log('   💡 This looks like an ARN or connection string, not JSON');
                console.log('   💡 The secret might need to be recreated in JSON format');
            }
            
            return false;
        }
        
    } catch (error) {
        console.log('❌ Secrets Manager access failed');
        console.log(`   Error: ${error.message}`);
        console.log(`   Code: ${error.code || 'Unknown'}`);
        
        if (error.code === 'ResourceNotFoundException') {
            console.log('   💡 The secret does not exist or ARN is incorrect');
        } else if (error.code === 'AccessDeniedException') {
            console.log('   💡 Lambda does not have permission to access this secret');
        }
        
        return false;
    }
}

async function testFromLambdaContext() {
    console.log('\n🚀 Testing from Lambda Context');
    console.log('='.repeat(40));
    
    // Simulate the Lambda environment
    const originalEnv = { ...process.env };
    
    // Check if we need to set Lambda-like environment
    if (!process.env.DB_SECRET_ARN) {
        console.log('⚠️  DB_SECRET_ARN not set in current environment');
        console.log('   This test needs to run in Lambda or with proper env vars');
        return false;
    }
    
    const success = await diagnoseSecretsManager();
    
    console.log('\n' + '='.repeat(40));
    console.log('📋 Diagnostic Summary');
    console.log('='.repeat(40));
    
    if (success) {
        console.log('✅ Secrets Manager is working correctly');
        console.log('   The database connectivity issue is elsewhere');
        console.log('   Check network connectivity or RDS status');
    } else {
        console.log('❌ Secrets Manager has issues');
        console.log('   This is the root cause of database connectivity failure');
        console.log('   Fix the secret format or permissions');
    }
    
    return success;
}

// Run if called directly
if (require.main === module) {
    testFromLambdaContext().catch(console.error);
}

module.exports = { diagnoseSecretsManager, testFromLambdaContext };