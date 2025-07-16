#!/usr/bin/env node

/**
 * Environment Variable Validation Script
 * 
 * This script validates that all required environment variables are properly configured
 * for the Financial Trading Platform deployment.
 */

const { execSync } = require('child_process');

// Required environment variables
const REQUIRED_ENV_VARS = {
  'DB_SECRET_ARN': {
    description: 'Database credentials secret ARN',
    example: 'arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:stocks-app-db-secret',
    required: true
  },
  'DB_ENDPOINT': {
    description: 'RDS database endpoint',
    example: 'stocks-db.cluster-xyz.us-east-1.rds.amazonaws.com',
    required: true
  },
  'API_KEY_ENCRYPTION_SECRET_ARN': {
    description: 'API key encryption secret ARN',
    example: 'arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:stocks-app-api-key-encryption',
    required: true
  },
  'WEBAPP_AWS_REGION': {
    description: 'AWS region for webapp deployment',
    example: 'us-east-1',
    required: true
  },
  'COGNITO_USER_POOL_ID': {
    description: 'Cognito User Pool ID',
    example: 'us-east-1_XXXXXXXXX',
    required: false
  },
  'COGNITO_CLIENT_ID': {
    description: 'Cognito App Client ID',
    example: 'abcdefghijklmnopqrstuvwxyz',
    required: false
  },
  'NODE_ENV': {
    description: 'Node.js environment',
    example: 'development',
    required: false,
    default: 'development'
  }
};

class EnvironmentValidator {
  constructor() {
    this.results = [];
    this.isValid = true;
    this.warnings = [];
  }

  async validate() {
    console.log('🔍 Validating Financial Trading Platform Environment Variables');
    console.log('=' .repeat(70));
    console.log();

    // Check if we're running in Lambda or local environment
    const isLambda = !!process.env.AWS_LAMBDA_FUNCTION_NAME;
    const isLocal = !isLambda;

    if (isLambda) {
      console.log('📍 Environment: AWS Lambda');
    } else {
      console.log('📍 Environment: Local Development');
    }
    console.log();

    // Validate each environment variable
    for (const [varName, config] of Object.entries(REQUIRED_ENV_VARS)) {
      this.validateVariable(varName, config);
    }

    // Check CloudFormation stack outputs if running locally
    if (isLocal) {
      await this.checkCloudFormationOutputs();
    }

    // Display results
    this.displayResults();

    // Return validation summary
    return {
      isValid: this.isValid,
      results: this.results,
      warnings: this.warnings
    };
  }

  validateVariable(varName, config) {
    const value = process.env[varName];
    const result = {
      name: varName,
      description: config.description,
      required: config.required,
      hasValue: !!value,
      isValid: true,
      message: null
    };

    // Check required variables
    if (config.required && !value) {
      result.isValid = false;
      result.message = `❌ MISSING: ${varName} is required but not set`;
      this.isValid = false;
    } else if (!config.required && !value && config.default) {
      result.message = `⚠️  USING DEFAULT: ${varName} not set, using default: ${config.default}`;
      this.warnings.push(result.message);
    } else if (!value) {
      result.message = `ℹ️  OPTIONAL: ${varName} not set (optional)`;
    } else {
      // Validate format
      const formatValidation = this.validateFormat(varName, value, config);
      if (formatValidation.isValid) {
        result.message = `✅ VALID: ${varName} is properly configured`;
      } else {
        result.message = `⚠️  FORMAT: ${varName} may have format issues: ${formatValidation.message}`;
        this.warnings.push(result.message);
      }
    }

    this.results.push(result);
    console.log(result.message);
  }

  validateFormat(varName, value, config) {
    switch (varName) {
      case 'DB_SECRET_ARN':
      case 'API_KEY_ENCRYPTION_SECRET_ARN':
        if (!value.includes('arn:aws:secretsmanager:')) {
          return { isValid: false, message: 'Not a valid Secrets Manager ARN' };
        }
        break;
      
      case 'DB_ENDPOINT':
        if (!value.includes('.rds.amazonaws.com') && !value.includes('.amazonaws.com')) {
          return { isValid: false, message: 'Not a valid RDS endpoint' };
        }
        break;
      
      case 'WEBAPP_AWS_REGION':
        if (!value.match(/^[a-z0-9-]+$/)) {
          return { isValid: false, message: 'Invalid AWS region format' };
        }
        break;
      
      case 'COGNITO_USER_POOL_ID':
        if (!value.match(/^[a-zA-Z0-9-_]+$/)) {
          return { isValid: false, message: 'Invalid Cognito User Pool ID format' };
        }
        break;
    }
    
    return { isValid: true };
  }

  async checkCloudFormationOutputs() {
    console.log();
    console.log('🔍 Checking CloudFormation Stack Outputs...');
    
    try {
      // Check main app stack
      const appStackOutputs = await this.getStackOutputs('stocks-app');
      if (appStackOutputs) {
        console.log('✅ Main app stack (stocks-app) found with outputs:');
        this.displayStackOutputs(appStackOutputs);
      } else {
        console.log('⚠️  Main app stack (stocks-app) not found or has no outputs');
        this.warnings.push('Main app stack not deployed');
      }

      // Check webapp Lambda stack
      const webappStackOutputs = await this.getStackOutputs('stocks-webapp-lambda');
      if (webappStackOutputs) {
        console.log('✅ Webapp Lambda stack (stocks-webapp-lambda) found with outputs:');
        this.displayStackOutputs(webappStackOutputs);
      } else {
        console.log('⚠️  Webapp Lambda stack (stocks-webapp-lambda) not found or has no outputs');
        this.warnings.push('Webapp Lambda stack not deployed');
      }
    } catch (error) {
      console.log(`⚠️  Could not check CloudFormation stacks: ${error.message}`);
      this.warnings.push('CloudFormation stack check failed');
    }
  }

  async getStackOutputs(stackName) {
    try {
      const command = `aws cloudformation describe-stacks --stack-name ${stackName} --query 'Stacks[0].Outputs' --output json`;
      const result = execSync(command, { encoding: 'utf8', stdio: 'pipe' });
      return JSON.parse(result);
    } catch (error) {
      return null;
    }
  }

  displayStackOutputs(outputs) {
    if (!outputs || outputs.length === 0) {
      console.log('   No outputs found');
      return;
    }

    outputs.forEach(output => {
      console.log(`   ${output.OutputKey}: ${output.OutputValue}`);
    });
  }

  displayResults() {
    console.log();
    console.log('📊 Validation Summary');
    console.log('=' .repeat(70));
    
    const validCount = this.results.filter(r => r.isValid && r.hasValue).length;
    const missingRequired = this.results.filter(r => !r.isValid && r.required).length;
    const totalRequired = this.results.filter(r => r.required).length;
    const warningCount = this.warnings.length;

    console.log(`✅ Valid: ${validCount}/${this.results.length} environment variables`);
    console.log(`❌ Missing Required: ${missingRequired}/${totalRequired} required variables`);
    console.log(`⚠️  Warnings: ${warningCount} warnings`);
    console.log();

    if (this.isValid) {
      console.log('🎉 Environment validation PASSED! All required variables are configured.');
    } else {
      console.log('💥 Environment validation FAILED! Some required variables are missing.');
      console.log();
      console.log('📝 Next Steps:');
      console.log('1. Deploy CloudFormation stacks in order: core → app → webapp-lambda');
      console.log('2. Check stack outputs for proper variable values');
      console.log('3. Update Lambda function environment variables if needed');
      console.log('4. See ENVIRONMENT_SETUP.md for detailed instructions');
    }

    if (this.warnings.length > 0) {
      console.log();
      console.log('⚠️  Warnings:');
      this.warnings.forEach(warning => console.log(`   ${warning}`));
    }

    console.log();
    console.log('📖 For detailed setup instructions, see ENVIRONMENT_SETUP.md');
  }
}

// Run validation if called directly
if (require.main === module) {
  const validator = new EnvironmentValidator();
  validator.validate()
    .then(result => {
      process.exit(result.isValid ? 0 : 1);
    })
    .catch(error => {
      console.error('💥 Validation failed with error:', error.message);
      process.exit(1);
    });
}

module.exports = EnvironmentValidator;