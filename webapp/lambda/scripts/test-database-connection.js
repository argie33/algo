#!/usr/bin/env node
/**
 * Database Connection Test Script
 * Tests database connectivity and provides diagnostic information
 */

const DatabaseConfigValidator = require('../utils/databaseConfigValidator');

async function testDatabaseConnection() {
  console.log('🔍 Database Connection Test Starting...\n');
  
  try {
    const validator = new DatabaseConfigValidator();
    
    // Step 1: Validate configuration
    console.log('📋 Step 1: Validating Database Configuration');
    console.log('=' .repeat(50));
    
    const configValidation = validator.validateConfig();
    
    if (configValidation.isValid) {
      console.log('✅ Database configuration is valid');
      console.log(`   Method: ${configValidation.config.method}`);
      if (configValidation.config.host) {
        console.log(`   Host: ${configValidation.config.host}`);
        console.log(`   User: ${configValidation.config.user}`);
        console.log(`   Database: ${configValidation.config.database}`);
      } else if (configValidation.config.secretArn) {
        console.log(`   Secret ARN: ${configValidation.config.secretArn}`);
      }
    } else {
      console.log('❌ Database configuration is invalid');
    }
    
    if (configValidation.errors.length > 0) {
      console.log('\n🚫 Configuration Errors:');
      configValidation.errors.forEach(error => {
        console.log(`   • ${error}`);
      });
    }
    
    if (configValidation.warnings.length > 0) {
      console.log('\n⚠️ Configuration Warnings:');
      configValidation.warnings.forEach(warning => {
        console.log(`   • ${warning}`);
      });
    }
    
    if (configValidation.suggestions.length > 0) {
      console.log('\n💡 Configuration Suggestions:');
      configValidation.suggestions.forEach(suggestion => {
        console.log(`   • ${suggestion}`);
      });
    }
    
    // Step 2: Test connection
    console.log('\n📡 Step 2: Testing Database Connection');
    console.log('=' .repeat(50));
    
    const startTime = Date.now();
    const connectionTest = await validator.testConnection();
    const testDuration = Date.now() - startTime;
    
    if (connectionTest.success) {
      console.log('✅ Database connection successful');
      console.log(`   Response time: ${testDuration}ms`);
      console.log(`   Server time: ${connectionTest.timestamp}`);
    } else {
      console.log('❌ Database connection failed');
      console.log(`   Error: ${connectionTest.error}`);
      console.log(`   Test duration: ${testDuration}ms`);
      
      if (connectionTest.suggestions && connectionTest.suggestions.length > 0) {
        console.log('\n💡 Connection Troubleshooting Suggestions:');
        connectionTest.suggestions.forEach(suggestion => {
          console.log(`   • ${suggestion}`);
        });
      }
    }
    
    // Step 3: Configuration recommendations
    console.log('\n🎯 Step 3: Configuration Recommendations');
    console.log('=' .repeat(50));
    
    const recommendations = validator.getConfigurationRecommendations();
    
    if (recommendations.length > 0) {
      recommendations.forEach(rec => {
        const priority = rec.priority.toUpperCase();
        const category = rec.category.toUpperCase();
        console.log(`${getPriorityIcon(rec.priority)} [${priority}] ${category}: ${rec.message}`);
        console.log(`   Action: ${rec.action}\n`);
      });
    } else {
      console.log('✅ No additional recommendations at this time');
    }
    
    // Step 4: Deployment checklist
    console.log('\n📋 Step 4: Deployment Checklist');
    console.log('=' .repeat(50));
    
    const checklist = validator.getDeploymentChecklist();
    
    checklist.forEach((item, index) => {
      console.log(`${index + 1}. ${item.item}`);
      console.log(`   Check: ${item.check}\n`);
    });
    
    // Step 5: Environment information
    console.log('\n🌍 Step 5: Environment Information');
    console.log('=' .repeat(50));
    
    console.log(`Node.js Version: ${process.version}`);
    console.log(`Platform: ${process.platform}`);
    console.log(`Architecture: ${process.arch}`);
    console.log(`NODE_ENV: ${process.env.NODE_ENV || 'not set'}`);
    console.log(`AWS_REGION: ${process.env.AWS_REGION || 'not set'}`);
    console.log(`IS_LAMBDA: ${!!process.env.AWS_LAMBDA_FUNCTION_NAME}`);
    
    console.log('\nEnvironment Variables:');
    const envVars = [
      'DB_HOST', 'DB_USER', 'DB_NAME', 'DB_SECRET_ARN',
      'AWS_REGION', 'NODE_ENV', 'ENVIRONMENT'
    ];
    
    envVars.forEach(varName => {
      const value = process.env[varName];
      if (value) {
        if (varName.includes('PASSWORD') || varName.includes('SECRET')) {
          console.log(`   ${varName}: [REDACTED]`);
        } else {
          console.log(`   ${varName}: ${value}`);
        }
      } else {
        console.log(`   ${varName}: not set`);
      }
    });
    
    // Summary
    console.log('\n📊 Summary');
    console.log('=' .repeat(50));
    
    if (configValidation.isValid && connectionTest.success) {
      console.log('🎉 All tests passed! Database is properly configured and accessible.');
      process.exit(0);
    } else if (configValidation.isValid && !connectionTest.success) {
      console.log('⚠️ Configuration is valid but connection failed. Check network and credentials.');
      process.exit(1);
    } else {
      console.log('❌ Configuration issues detected. Please fix configuration before testing connection.');
      process.exit(1);
    }
    
  } catch (error) {
    console.error('\n💥 Test script failed with error:');
    console.error(error.message);
    console.error('\nStack trace:');
    console.error(error.stack);
    process.exit(1);
  }
}

function getPriorityIcon(priority) {
  switch (priority) {
    case 'high': return '🔴';
    case 'medium': return '🟡';
    case 'low': return '🟢';
    default: return '⚪';
  }
}

// Run the test if called directly
if (require.main === module) {
  testDatabaseConnection().catch(error => {
    console.error('Unhandled error:', error);
    process.exit(1);
  });
}

module.exports = testDatabaseConnection;