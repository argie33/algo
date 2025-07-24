#!/usr/bin/env node

/**
 * Enhanced API Key Service Deployment Script
 * 
 * Automates the deployment of the long-term Parameter Store-only solution
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// Import AWS clients
const { SSMClient, PutParameterCommand, GetParameterCommand } = require('@aws-sdk/client-ssm');
const { IAMClient, PutRolePolicyCommand, GetRolePolicyCommand } = require('@aws-sdk/client-iam');
const { LambdaClient, UpdateFunctionConfigurationCommand } = require('@aws-sdk/client-lambda');

class EnhancedApiKeyDeployment {
  constructor() {
    this.region = process.env.AWS_REGION || 'us-east-1';
    
    this.ssm = new SSMClient({ region: this.region });
    this.iam = new IAMClient({ region: this.region });
    this.lambda = new LambdaClient({ region: this.region });
    
    this.deploymentConfig = {
      parameterPrefix: '/financial-platform/users',
      lambdaFunctionName: process.env.LAMBDA_FUNCTION_NAME || 'financial-dashboard-api',
      iamRoleName: process.env.LAMBDA_ROLE_NAME || 'lambda-execution-role',
      kmsKeyId: process.env.KMS_KEY_ID || 'alias/aws/ssm'
    };
    
    this.deploymentStats = {
      startTime: new Date().toISOString(),
      steps: [],
      errors: [],
      warnings: []
    };
  }

  /**
   * Main deployment orchestrator
   */
  async deploy(options = {}) {
    const {
      skipPreChecks = false,
      skipIamUpdates = false,
      skipParameterSetup = false,
      skipLambdaUpdate = false,
      dryRun = false
    } = options;

    console.log('🚀 Starting Enhanced API Key Service Deployment');
    console.log(`📍 Region: ${this.region}`);
    console.log(`🏷️  Lambda Function: ${this.deploymentConfig.lambdaFunctionName}`);
    console.log(`👤 IAM Role: ${this.deploymentConfig.iamRoleName}`);
    console.log(`🔑 KMS Key: ${this.deploymentConfig.kmsKeyId}`);
    console.log(`🧪 Dry Run: ${dryRun}`);
    console.log('');

    try {
      // Step 1: Pre-deployment checks
      if (!skipPreChecks) {
        await this.runPreDeploymentChecks();
      }

      // Step 2: Update IAM permissions
      if (!skipIamUpdates) {
        await this.updateIamPermissions(dryRun);
      }

      // Step 3: Setup Parameter Store structure
      if (!skipParameterSetup) {
        await this.setupParameterStoreStructure(dryRun);
      }

      // Step 4: Update Lambda configuration
      if (!skipLambdaUpdate) {
        await this.updateLambdaConfiguration(dryRun);
      }

      // Step 5: Validate deployment
      await this.validateDeployment();

      // Step 6: Generate deployment report
      await this.generateDeploymentReport();

      console.log('✅ Enhanced API Key Service deployment completed successfully!');
      return this.deploymentStats;

    } catch (error) {
      console.error('❌ Deployment failed:', error.message);
      this.deploymentStats.errors.push({
        step: 'deployment',
        error: error.message,
        timestamp: new Date().toISOString()
      });
      throw error;
    }
  }

  /**
   * Run pre-deployment checks
   */
  async runPreDeploymentChecks() {
    console.log('🔍 Running pre-deployment checks...');
    
    const checks = [];

    try {
      // Check AWS credentials
      try {
        await this.ssm.send(new GetParameterCommand({ Name: '/aws/service/global-infrastructure/regions/us-east-1' }));
        checks.push({ name: 'AWS Credentials', status: 'PASS' });
      } catch (error) {
        checks.push({ name: 'AWS Credentials', status: 'FAIL', error: error.message });
      }

      // Check required files exist
      const requiredFiles = [
        'utils/enhancedApiKeyService.js',
        'utils/enhancedCircuitBreaker.js',
        'routes/settings-enhanced.js',
        'routes/settings-integration.js',
        'utils/apiKeyMigrationUtility.js'
      ];

      for (const file of requiredFiles) {
        const filePath = path.join(__dirname, '..', file);
        if (fs.existsSync(filePath)) {
          checks.push({ name: `File: ${file}`, status: 'PASS' });
        } else {
          checks.push({ name: `File: ${file}`, status: 'FAIL', error: 'File not found' });
        }
      }

      // Check environment variables
      const requiredEnvVars = ['AWS_REGION'];
      for (const envVar of requiredEnvVars) {
        if (process.env[envVar]) {
          checks.push({ name: `Env Var: ${envVar}`, status: 'PASS' });
        } else {
          checks.push({ name: `Env Var: ${envVar}`, status: 'WARN', error: 'Not set - using default' });
        }
      }

      this.deploymentStats.steps.push({
        step: 'pre-checks',
        status: 'completed',
        checks,
        timestamp: new Date().toISOString()
      });

      const failures = checks.filter(c => c.status === 'FAIL');
      if (failures.length > 0) {
        throw new Error(`Pre-deployment checks failed: ${failures.map(f => f.name).join(', ')}`);
      }

      console.log(`✅ Pre-deployment checks passed (${checks.length} checks)`);

    } catch (error) {
      console.error('❌ Pre-deployment checks failed:', error.message);
      throw error;
    }
  }

  /**
   * Update IAM permissions for Parameter Store access
   */
  async updateIamPermissions(dryRun = false) {
    console.log('👤 Updating IAM permissions...');

    const policyDocument = {
      Version: '2012-10-17',
      Statement: [
        {
          Sid: 'ParameterStoreAccess',
          Effect: 'Allow',
          Action: [
            'ssm:GetParameter',
            'ssm:GetParameters',
            'ssm:GetParametersByPath',
            'ssm:PutParameter',
            'ssm:DeleteParameter',
            'ssm:AddTagsToResource',
            'ssm:ListTagsForResource'
          ],
          Resource: [
            `arn:aws:ssm:${this.region}:*:parameter${this.deploymentConfig.parameterPrefix}/*`,
            `arn:aws:ssm:${this.region}:*:parameter${this.deploymentConfig.parameterPrefix}/health-check*`
          ]
        },
        {
          Sid: 'KMSAccess',
          Effect: 'Allow',
          Action: [
            'kms:Encrypt',
            'kms:Decrypt',
            'kms:ReEncrypt*',
            'kms:GenerateDataKey*',
            'kms:DescribeKey'
          ],
          Resource: [
            `arn:aws:kms:${this.region}:*:key/*`
          ]
        },
        {
          Sid: 'CloudWatchMetrics',
          Effect: 'Allow',
          Action: [
            'cloudwatch:PutMetricData'
          ],
          Resource: '*',
          Condition: {
            StringEquals: {
              'cloudwatch:namespace': [
                'FinancialPlatform/ApiKeys',
                'FinancialPlatform/CircuitBreaker'
              ]
            }
          }
        }
      ]
    };

    try {
      if (dryRun) {
        console.log('🧪 [DRY RUN] Would update IAM policy with:');
        console.log(JSON.stringify(policyDocument, null, 2));
      } else {
        const policyName = 'EnhancedApiKeyServicePolicy';
        
        await this.iam.send(new PutRolePolicyCommand({
          RoleName: this.deploymentConfig.iamRoleName,
          PolicyName: policyName,
          PolicyDocument: JSON.stringify(policyDocument)
        }));

        console.log(`✅ IAM policy '${policyName}' updated successfully`);
      }

      this.deploymentStats.steps.push({
        step: 'iam-permissions',
        status: 'completed',
        policyName: 'EnhancedApiKeyServicePolicy',
        dryRun,
        timestamp: new Date().toISOString()
      });

    } catch (error) {
      console.error('❌ IAM permission update failed:', error.message);
      
      if (error.name === 'NoSuchEntityException') {
        this.deploymentStats.warnings.push({
          step: 'iam-permissions',
          warning: `IAM role '${this.deploymentConfig.iamRoleName}' not found - manual IAM setup required`,
          timestamp: new Date().toISOString()
        });
        console.log(`⚠️  IAM role '${this.deploymentConfig.iamRoleName}' not found - skipping IAM updates`);
      } else {
        throw error;
      }
    }
  }

  /**
   * Setup Parameter Store structure
   */
  async setupParameterStoreStructure(dryRun = false) {
    console.log('📦 Setting up Parameter Store structure...');

    const setupParameters = [
      {
        name: `${this.deploymentConfig.parameterPrefix}/config/version`,
        value: JSON.stringify({
          version: '2.0',
          service: 'EnhancedApiKeyService',
          deployed: new Date().toISOString(),
          features: [
            'circuit-breaker',
            'caching',
            'monitoring',
            'user-isolation'
          ]
        }),
        description: 'Enhanced API Key Service configuration'
      },
      {
        name: `${this.deploymentConfig.parameterPrefix}/config/circuit-breaker`,
        value: JSON.stringify({
          failureThreshold: 5,
          successThreshold: 3,
          timeout: 30000,
          userFailureThreshold: 3,
          globalFailureThreshold: 20,
          enabled: true
        }),
        description: 'Circuit breaker configuration'
      }
    ];

    try {
      for (const param of setupParameters) {
        if (dryRun) {
          console.log(`🧪 [DRY RUN] Would create parameter: ${param.name}`);
          console.log(`   Value: ${param.value}`);
        } else {
          try {
            await this.ssm.send(new PutParameterCommand({
              Name: param.name,
              Value: param.value,
              Type: 'String',
              Overwrite: true,
              Description: param.description,
              Tags: [
                { Key: 'Service', Value: 'EnhancedApiKeyService' },
                { Key: 'Environment', Value: process.env.NODE_ENV || 'production' },
                { Key: 'DeployedBy', Value: 'deploy-enhanced-api-keys.js' }
              ]
            }));

            console.log(`✅ Parameter '${param.name}' created successfully`);

          } catch (paramError) {
            console.error(`❌ Failed to create parameter '${param.name}':`, paramError.message);
            this.deploymentStats.warnings.push({
              step: 'parameter-setup',
              warning: `Failed to create ${param.name}: ${paramError.message}`,
              timestamp: new Date().toISOString()
            });
          }
        }
      }

      this.deploymentStats.steps.push({
        step: 'parameter-setup',
        status: 'completed',
        parametersCreated: setupParameters.length,
        dryRun,
        timestamp: new Date().toISOString()
      });

      console.log(`✅ Parameter Store structure setup completed (${setupParameters.length} parameters)`);

    } catch (error) {
      console.error('❌ Parameter Store setup failed:', error.message);
      throw error;
    }
  }

  /**
   * Update Lambda configuration
   */
  async updateLambdaConfiguration(dryRun = false) {
    console.log('⚡ Updating Lambda configuration...');

    const environmentVariables = {
      USE_ENHANCED_API_KEY_SERVICE: 'true',
      ENHANCED_API_KEY_VERSION: '2.0',
      CIRCUIT_BREAKER_ENABLED: 'true',
      PARAMETER_STORE_PREFIX: this.deploymentConfig.parameterPrefix,
      CLOUDWATCH_METRICS_ENABLED: 'true'
    };

    try {
      if (dryRun) {
        console.log('🧪 [DRY RUN] Would update Lambda environment variables:');
        console.log(JSON.stringify(environmentVariables, null, 2));
      } else {
        // Get current configuration
        let currentConfig;
        try {
          const { Configuration } = await this.lambda.send({
            FunctionName: this.deploymentConfig.lambdaFunctionName
          });
          currentConfig = Configuration;
        } catch (error) {
          console.log(`⚠️  Could not retrieve current Lambda configuration: ${error.message}`);
          currentConfig = { Environment: { Variables: {} } };
        }

        // Merge environment variables
        const updatedVariables = {
          ...(currentConfig.Environment?.Variables || {}),
          ...environmentVariables
        };

        await this.lambda.send(new UpdateFunctionConfigurationCommand({
          FunctionName: this.deploymentConfig.lambdaFunctionName,
          Environment: {
            Variables: updatedVariables
          }
        }));

        console.log(`✅ Lambda function '${this.deploymentConfig.lambdaFunctionName}' configuration updated`);
      }

      this.deploymentStats.steps.push({
        step: 'lambda-configuration',
        status: 'completed',
        environmentVariables,
        dryRun,
        timestamp: new Date().toISOString()
      });

    } catch (error) {
      console.error('❌ Lambda configuration update failed:', error.message);
      
      if (error.name === 'ResourceNotFoundException') {
        this.deploymentStats.warnings.push({
          step: 'lambda-configuration',
          warning: `Lambda function '${this.deploymentConfig.lambdaFunctionName}' not found - manual configuration required`,
          timestamp: new Date().toISOString()
        });
        console.log(`⚠️  Lambda function '${this.deploymentConfig.lambdaFunctionName}' not found - skipping Lambda updates`);
      } else {
        throw error;
      }
    }
  }

  /**
   * Validate deployment
   */
  async validateDeployment() {
    console.log('🔍 Validating deployment...');

    const validationResults = [];

    try {
      // Test Parameter Store connectivity
      try {
        const testParam = `${this.deploymentConfig.parameterPrefix}/deployment-test-${Date.now()}`;
        
        await this.ssm.send(new PutParameterCommand({
          Name: testParam,
          Value: JSON.stringify({ test: true, timestamp: new Date().toISOString() }),
          Type: 'String',
          Overwrite: true
        }));

        await this.ssm.send(new GetParameterCommand({ Name: testParam }));
        
        // Cleanup test parameter
        await this.ssm.send({ Name: testParam });

        validationResults.push({ name: 'Parameter Store Connectivity', status: 'PASS' });

      } catch (error) {
        validationResults.push({ 
          name: 'Parameter Store Connectivity', 
          status: 'FAIL', 
          error: error.message 
        });
      }

      // Validate configuration parameters exist
      const configParams = [
        `${this.deploymentConfig.parameterPrefix}/config/version`,
        `${this.deploymentConfig.parameterPrefix}/config/circuit-breaker`
      ];

      for (const param of configParams) {
        try {
          await this.ssm.send(new GetParameterCommand({ Name: param }));
          validationResults.push({ name: `Config Parameter: ${param}`, status: 'PASS' });
        } catch (error) {
          validationResults.push({ 
            name: `Config Parameter: ${param}`, 
            status: 'FAIL', 
            error: error.message 
          });
        }
      }

      this.deploymentStats.steps.push({
        step: 'validation',
        status: 'completed',
        validationResults,
        timestamp: new Date().toISOString()
      });

      const failures = validationResults.filter(r => r.status === 'FAIL');
      if (failures.length > 0) {
        console.log(`⚠️  Validation completed with ${failures.length} failures`);
        this.deploymentStats.warnings.push({
          step: 'validation',
          warning: `${failures.length} validation checks failed`,
          details: failures,
          timestamp: new Date().toISOString()
        });
      } else {
        console.log(`✅ Deployment validation passed (${validationResults.length} checks)`);
      }

    } catch (error) {
      console.error('❌ Deployment validation failed:', error.message);
      throw error;
    }
  }

  /**
   * Generate deployment report
   */
  async generateDeploymentReport() {
    console.log('📊 Generating deployment report...');

    const report = {
      deployment: {
        version: '2.0',
        timestamp: new Date().toISOString(),
        duration: Date.now() - new Date(this.deploymentStats.startTime).getTime(),
        region: this.region,
        configuration: this.deploymentConfig
      },
      summary: {
        totalSteps: this.deploymentStats.steps.length,
        completedSteps: this.deploymentStats.steps.filter(s => s.status === 'completed').length,
        errors: this.deploymentStats.errors.length,
        warnings: this.deploymentStats.warnings.length
      },
      steps: this.deploymentStats.steps,
      errors: this.deploymentStats.errors,
      warnings: this.deploymentStats.warnings,
      nextSteps: [
        'Update application code to use enhanced API key service',
        'Update frontend to use enhanced endpoints',
        'Monitor CloudWatch metrics for service health',
        'Plan migration from legacy service if applicable'
      ]
    };

    // Write report to file
    const reportPath = path.join(__dirname, `deployment-report-${Date.now()}.json`);
    fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));

    console.log(`📄 Deployment report saved to: ${reportPath}`);
    console.log('');
    console.log('📋 Deployment Summary:');
    console.log(`   ✅ Steps completed: ${report.summary.completedSteps}/${report.summary.totalSteps}`);
    console.log(`   ⚠️  Warnings: ${report.summary.warnings}`);
    console.log(`   ❌ Errors: ${report.summary.errors}`);
    console.log(`   ⏱️  Duration: ${Math.round(report.deployment.duration / 1000)}s`);

    return report;
  }
}

// CLI execution
if (require.main === module) {
  const deployment = new EnhancedApiKeyDeployment();
  
  // Parse command line arguments
  const args = process.argv.slice(2);
  const options = {
    skipPreChecks: args.includes('--skip-pre-checks'),
    skipIamUpdates: args.includes('--skip-iam'),
    skipParameterSetup: args.includes('--skip-parameters'),
    skipLambdaUpdate: args.includes('--skip-lambda'),
    dryRun: args.includes('--dry-run')
  };

  deployment.deploy(options)
    .then(stats => {
      console.log('🎉 Deployment completed successfully!');
      process.exit(0);
    })
    .catch(error => {
      console.error('💥 Deployment failed:', error.message);
      process.exit(1);
    });
}

module.exports = EnhancedApiKeyDeployment;