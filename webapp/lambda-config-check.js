// Lambda Configuration Checker
// Run this as a test Lambda to debug the configuration

exports.handler = async (event, context) => {
    console.log('=== Lambda Configuration Debug ===');
    
    const config = {
        environment: {
            NODE_ENV: process.env.NODE_ENV,
            AWS_REGION: process.env.AWS_REGION,
            AWS_DEFAULT_REGION: process.env.AWS_DEFAULT_REGION,
            WEBAPP_AWS_REGION: process.env.WEBAPP_AWS_REGION,
            DB_SECRET_ARN: process.env.DB_SECRET_ARN ? 'SET' : 'MISSING',
            DB_SECRET_ARN_VALUE: process.env.DB_SECRET_ARN
        },
        aws: {
            region: context.invokedFunctionArn.split(':')[3],
            accountId: context.invokedFunctionArn.split(':')[4],
            functionName: context.functionName,
            functionVersion: context.functionVersion
        },
        networking: {
            hasVpcConfig: !!process.env.AWS_LAMBDA_VPC_SUBNET_IDS,
            subnetIds: process.env.AWS_LAMBDA_VPC_SUBNET_IDS,
            securityGroupIds: process.env.AWS_LAMBDA_VPC_SECURITY_GROUP_IDS
        }
    };
    
    console.log('Configuration:', JSON.stringify(config, null, 2));
    
    // Test Secrets Manager access
    let secretsTest = 'NOT_TESTED';
    if (process.env.DB_SECRET_ARN) {
        try {
            const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');
            const client = new SecretsManagerClient({ region: process.env.AWS_REGION || 'us-east-1' });
            const command = new GetSecretValueCommand({ SecretId: process.env.DB_SECRET_ARN });
            
            console.log('Testing Secrets Manager access...');
            const result = await client.send(command);
            secretsTest = 'SUCCESS';
            console.log('✅ Secrets Manager access successful');
            
            // Parse the secret to check database credentials
            const secret = JSON.parse(result.SecretString);
            const dbConfig = {
                host: secret.host || 'MISSING',
                port: secret.port || 'MISSING', 
                database: secret.dbname || 'MISSING',
                username: secret.username || 'MISSING',
                hasPassword: !!secret.password
            };
            console.log('Database config from secret:', dbConfig);
            
        } catch (error) {
            secretsTest = `FAILED: ${error.message}`;
            console.error('❌ Secrets Manager test failed:', error);
        }
    } else {
        secretsTest = 'SKIPPED - No DB_SECRET_ARN';
    }
    
    // Test basic database connection (if we have credentials)
    let dbConnectionTest = 'NOT_TESTED';
    if (secretsTest === 'SUCCESS') {
        try {
            console.log('Testing database connection...');
            
            // Import database utilities
            const { initializeDatabase } = require('./utils/database');
            
            const pool = await initializeDatabase();
            if (pool) {
                dbConnectionTest = 'SUCCESS';
                console.log('✅ Database connection successful');
            } else {
                dbConnectionTest = 'FAILED - No pool returned';
            }
            
        } catch (error) {
            dbConnectionTest = `FAILED: ${error.message}`;
            console.error('❌ Database connection test failed:', error);
        }
    }
    
    const diagnostics = {
        timestamp: new Date().toISOString(),
        configuration: config,
        tests: {
            secretsManager: secretsTest,
            databaseConnection: dbConnectionTest
        },
        recommendations: []
    };
    
    // Generate recommendations
    if (!process.env.DB_SECRET_ARN) {
        diagnostics.recommendations.push('Set DB_SECRET_ARN environment variable');
    }
    
    if (!process.env.AWS_REGION && !process.env.AWS_DEFAULT_REGION) {
        diagnostics.recommendations.push('Set AWS_REGION environment variable');
    }
    
    if (secretsTest.includes('FAILED')) {
        diagnostics.recommendations.push('Check IAM permissions for Secrets Manager');
        diagnostics.recommendations.push('Verify DB_SECRET_ARN points to existing secret');
    }
    
    if (!config.networking.hasVpcConfig) {
        diagnostics.recommendations.push('Configure VPC settings for database access');
    }
    
    console.log('=== Diagnostics Complete ===');
    console.log(JSON.stringify(diagnostics, null, 2));
    
    return {
        statusCode: 200,
        headers: {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        body: JSON.stringify({
            message: 'Lambda Configuration Diagnostics',
            status: secretsTest === 'SUCCESS' && dbConnectionTest === 'SUCCESS' ? 'HEALTHY' : 'ISSUES_FOUND',
            diagnostics: diagnostics
        }, null, 2)
    };
};