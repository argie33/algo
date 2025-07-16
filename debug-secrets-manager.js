#!/usr/bin/env node

/**
 * AWS Secrets Manager Diagnostic Script
 * 
 * Diagnoses the "Unexpected token o in JSON at position 1" error
 * by testing Secrets Manager access and JSON parsing
 */

// require('dotenv').config(); // Skip dotenv for now
const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');

// Configure AWS SDK
const secretsManager = new SecretsManagerClient({
    region: process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || 'us-east-1'
});

async function diagnosticSecretsManager() {
    console.log('🔍 AWS Secrets Manager Diagnostic Script');
    console.log('========================================');
    
    const secretArn = process.env.DB_SECRET_ARN;
    console.log(`🔑 Secret ARN: ${secretArn}`);
    console.log(`🌍 AWS Region: ${process.env.AWS_REGION || 'us-east-1'}`);
    console.log(`🔧 Node Environment: ${process.env.NODE_ENV || 'development'}`);
    
    if (!secretArn) {
        console.error('❌ DB_SECRET_ARN environment variable not set');
        console.log('💡 Expected format: arn:aws:secretsmanager:region:account:secret:name');
        return;
    }
    
    try {
        console.log('\n🔄 Step 1: Testing Secrets Manager connectivity...');
        const command = new GetSecretValueCommand({ SecretId: secretArn });
        
        console.log('📡 Sending GetSecretValueCommand...');
        const startTime = Date.now();
        const response = await secretsManager.send(command);
        const responseTime = Date.now() - startTime;
        
        console.log(`✅ Secrets Manager responded in ${responseTime}ms`);
        console.log(`📊 Response metadata:`, {
            arn: response.ARN,
            name: response.Name,
            versionId: response.VersionId,
            versionStages: response.VersionStages,
            createdDate: response.CreatedDate
        });
        
        console.log('\n🔄 Step 2: Analyzing SecretString...');
        console.log(`📝 SecretString type: ${typeof response.SecretString}`);
        console.log(`📏 SecretString length: ${response.SecretString?.length || 'undefined'}`);
        
        // Show first few characters to debug the parsing issue
        if (response.SecretString) {
            const first10 = response.SecretString.substring(0, 10);
            console.log(`🔍 First 10 characters: "${first10}"`);
            console.log(`🔢 Character codes: [${first10.split('').map(c => c.charCodeAt(0)).join(', ')}]`);
            
            // Check for common issues
            if (response.SecretString.startsWith('object')) {
                console.error('❌ ISSUE: SecretString starts with "object" - likely stringified object');
            }
            
            if (!response.SecretString.startsWith('{')) {
                console.error('❌ ISSUE: SecretString does not start with "{" - not valid JSON');
            }
        } else {
            console.error('❌ ISSUE: SecretString is undefined or null');
            return;
        }
        
        console.log('\n🔄 Step 3: Testing JSON parsing...');
        try {
            const secret = JSON.parse(response.SecretString);
            console.log('✅ JSON parsing successful');
            console.log('🔑 Secret keys:', Object.keys(secret));
            
            // Validate required keys
            const requiredKeys = ['username', 'password', 'host'];
            const missingKeys = requiredKeys.filter(key => !secret[key]);
            
            if (missingKeys.length > 0) {
                console.error(`❌ Missing required keys: ${missingKeys.join(', ')}`);
            } else {
                console.log('✅ All required keys present');
            }
            
            // Show sanitized configuration
            console.log('🔧 Database configuration:');
            console.log(`   Host: ${secret.host || 'MISSING'}`);
            console.log(`   Port: ${secret.port || 5432}`);
            console.log(`   Database: ${secret.dbname || 'stocks'}`);
            console.log(`   Username: ${secret.username || 'MISSING'}`);
            console.log(`   Password: ${secret.password ? '[SET]' : 'MISSING'}`);
            
        } catch (parseError) {
            console.error('❌ JSON parsing failed:', parseError.message);
            console.error('🔍 Parse error details:', {
                name: parseError.name,
                message: parseError.message,
                stack: parseError.stack?.split('\n')[0]
            });
            
            // Try to identify the problematic character
            const errorMatch = parseError.message.match(/position (\d+)/);
            if (errorMatch) {
                const position = parseInt(errorMatch[1]);
                const problematicChar = response.SecretString[position];
                console.error(`🎯 Problematic character at position ${position}: "${problematicChar}" (code: ${problematicChar?.charCodeAt(0) || 'undefined'})`);
                
                // Show context around the error
                const start = Math.max(0, position - 10);
                const end = Math.min(response.SecretString.length, position + 10);
                const context = response.SecretString.substring(start, end);
                console.error(`📄 Context around error: "${context}"`);
            }
        }
        
    } catch (error) {
        console.error('❌ Secrets Manager access failed:', error.message);
        console.error('🔍 Error details:', {
            name: error.name,
            code: error.code,
            statusCode: error.$metadata?.httpStatusCode,
            requestId: error.$metadata?.requestId
        });
        
        // Common troubleshooting suggestions
        console.log('\n💡 Troubleshooting suggestions:');
        console.log('1. Verify the secret exists in the specified region');
        console.log('2. Check IAM permissions for SecretsManager:GetSecretValue');
        console.log('3. Ensure the secret ARN is correctly formatted');
        console.log('4. Verify the AWS credentials have access to this secret');
    }
}

// Self-executing diagnostic
if (require.main === module) {
    diagnosticSecretsManager()
        .then(() => {
            console.log('\n✅ Secrets Manager diagnostic complete');
            process.exit(0);
        })
        .catch(error => {
            console.error('\n❌ Diagnostic script failed:', error.message);
            process.exit(1);
        });
}

module.exports = { diagnosticSecretsManager };