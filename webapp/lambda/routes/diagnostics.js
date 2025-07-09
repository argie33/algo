const express = require('express');
const router = express.Router();

// Comprehensive diagnostic endpoint to help troubleshoot configuration issues
router.get('/comprehensive', async (req, res) => {
  try {
    console.log('=== Comprehensive Lambda Diagnostics Endpoint Called ===');
    
    const { DatabaseConnectivityTest } = require('../utils/dbConnectivityTest');
    const dbTest = new DatabaseConnectivityTest();
    
    const testResults = await dbTest.runComprehensiveTests();
    const summary = dbTest.generateSummaryReport();
    
    res.json({
      success: true,
      message: 'Comprehensive Lambda Database Diagnostics',
      summary,
      detailedResults: testResults
    });
    
  } catch (error) {
    console.error('Comprehensive diagnostics endpoint error:', error);
    res.status(500).json({
      success: false,
      error: 'Comprehensive diagnostics failed',
      message: error.message,
      stack: error.stack
    });
  }
});

// Original diagnostic endpoint to help troubleshoot configuration issues
router.get('/', async (req, res) => {
  try {
    console.log('=== Lambda Diagnostics Endpoint Called ===');
    
    const diagnostics = {
      timestamp: new Date().toISOString(),
      environment: {
        NODE_ENV: process.env.NODE_ENV || 'NOT_SET',
        AWS_REGION: process.env.AWS_REGION || 'NOT_SET',
        AWS_DEFAULT_REGION: process.env.AWS_DEFAULT_REGION || 'NOT_SET',
        WEBAPP_AWS_REGION: process.env.WEBAPP_AWS_REGION || 'NOT_SET',
        DB_SECRET_ARN: process.env.DB_SECRET_ARN ? 'SET' : 'NOT_SET',
        DB_SECRET_ARN_VALUE: process.env.DB_SECRET_ARN || 'NOT_SET'
      },
      vpc: {
        hasVpcConfig: !!(process.env.AWS_LAMBDA_VPC_SUBNET_IDS && process.env.AWS_LAMBDA_VPC_SECURITY_GROUP_IDS),
        subnetIds: process.env.AWS_LAMBDA_VPC_SUBNET_IDS || 'NOT_SET',
        securityGroupIds: process.env.AWS_LAMBDA_VPC_SECURITY_GROUP_IDS || 'NOT_SET'
      },
      lambda: {
        functionName: process.env.AWS_LAMBDA_FUNCTION_NAME || 'NOT_SET',
        functionVersion: process.env.AWS_LAMBDA_FUNCTION_VERSION || 'NOT_SET',
        memorySize: process.env.AWS_LAMBDA_FUNCTION_MEMORY_SIZE || 'NOT_SET',
        timeout: process.env.AWS_LAMBDA_FUNCTION_TIMEOUT || 'NOT_SET',
        runtime: process.env.AWS_EXECUTION_ENV || 'NOT_SET'
      },
      tests: {
        secretsManager: 'NOT_TESTED',
        databaseConnection: 'NOT_TESTED'
      }
    };

    console.log('Environment variables check:', diagnostics.environment);
    console.log('VPC configuration:', diagnostics.vpc);

    // Test Secrets Manager access if we have the ARN
    if (process.env.DB_SECRET_ARN && process.env.DB_SECRET_ARN !== 'NOT_SET') {
      try {
        console.log('Testing Secrets Manager access...');
        const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');
        
        const client = new SecretsManagerClient({ 
          region: process.env.AWS_REGION || process.env.AWS_DEFAULT_REGION || 'us-east-1' 
        });
        
        const command = new GetSecretValueCommand({ 
          SecretId: process.env.DB_SECRET_ARN 
        });
        
        const result = await client.send(command);
        diagnostics.tests.secretsManager = 'SUCCESS';
        
        // Parse and validate the secret content
        try {
          const secret = JSON.parse(result.SecretString);
          diagnostics.databaseCredentials = {
            hasHost: !!secret.host,
            hasPort: !!secret.port,
            hasUsername: !!secret.username,
            hasPassword: !!secret.password,
            hasDbname: !!secret.dbname,
            host: secret.host || 'MISSING',
            port: secret.port || 'MISSING',
            dbname: secret.dbname || 'MISSING'
          };
          console.log('✅ Secrets Manager access successful');
          console.log('Database config from secret:', {
            host: secret.host,
            port: secret.port,
            dbname: secret.dbname,
            hasPassword: !!secret.password
          });
        } catch (parseError) {
          diagnostics.tests.secretsManager = `SUCCESS_BUT_INVALID_JSON: ${parseError.message}`;
        }
        
      } catch (error) {
        diagnostics.tests.secretsManager = `FAILED: ${error.name} - ${error.message}`;
        console.error('❌ Secrets Manager test failed:', error);
      }
    } else {
      diagnostics.tests.secretsManager = 'SKIPPED - No DB_SECRET_ARN';
    }

    // Test database connection if Secrets Manager worked
    if (diagnostics.tests.secretsManager === 'SUCCESS') {
      try {
        console.log('Testing database connection...');
        
        // Try to initialize database connection
        const { initializeDatabase } = require('../utils/database');
        const pool = await Promise.race([
          initializeDatabase(),
          new Promise((_, reject) => 
            setTimeout(() => reject(new Error('Database initialization timeout')), 15000)
          )
        ]);
        
        if (pool) {
          // Test a simple query
          const { query } = require('../utils/database');
          await query('SELECT 1 as test');
          diagnostics.tests.databaseConnection = 'SUCCESS';
          console.log('✅ Database connection successful');
        } else {
          diagnostics.tests.databaseConnection = 'FAILED - No pool returned';
        }
        
      } catch (error) {
        diagnostics.tests.databaseConnection = `FAILED: ${error.name} - ${error.message}`;
        console.error('❌ Database connection test failed:', error);
      }
    }

    // Generate recommendations
    const recommendations = [];
    
    if (diagnostics.environment.DB_SECRET_ARN === 'NOT_SET') {
      recommendations.push('Set DB_SECRET_ARN environment variable in Lambda configuration');
    }
    
    if (diagnostics.environment.AWS_REGION === 'NOT_SET' && diagnostics.environment.AWS_DEFAULT_REGION === 'NOT_SET') {
      recommendations.push('Set AWS_REGION or AWS_DEFAULT_REGION environment variable');
    }
    
    if (!diagnostics.vpc.hasVpcConfig) {
      recommendations.push('Configure VPC settings if database is in private subnet');
    }
    
    if (diagnostics.tests.secretsManager.includes('FAILED')) {
      if (diagnostics.tests.secretsManager.includes('AccessDenied')) {
        recommendations.push('Add secretsmanager:GetSecretValue permission to Lambda execution role');
      } else if (diagnostics.tests.secretsManager.includes('ResourceNotFoundException')) {
        recommendations.push('Verify DB_SECRET_ARN points to existing secret in correct region');
      } else {
        recommendations.push('Check IAM permissions and secret ARN configuration');
      }
    }
    
    if (diagnostics.tests.databaseConnection.includes('FAILED')) {
      if (diagnostics.tests.databaseConnection.includes('timeout')) {
        recommendations.push('Check VPC/security group configuration for database access');
        recommendations.push('Ensure Lambda can reach database (port 5432)');
      } else if (diagnostics.tests.databaseConnection.includes('ECONNREFUSED')) {
        recommendations.push('Database may be down or unreachable from Lambda');
      } else {
        recommendations.push('Review database connection configuration and credentials');
      }
    }

    diagnostics.recommendations = recommendations;
    diagnostics.status = (diagnostics.tests.secretsManager === 'SUCCESS' && diagnostics.tests.databaseConnection === 'SUCCESS') ? 'HEALTHY' : 'ISSUES_FOUND';

    console.log('=== Diagnostics Complete ===');
    console.log('Status:', diagnostics.status);
    console.log('Recommendations:', recommendations);

    res.json({
      success: true,
      message: 'Lambda Configuration Diagnostics',
      diagnostics: diagnostics
    });

  } catch (error) {
    console.error('Diagnostics endpoint error:', error);
    res.status(500).json({
      success: false,
      error: 'Diagnostics failed',
      message: error.message,
      stack: error.stack
    });
  }
});

module.exports = router;