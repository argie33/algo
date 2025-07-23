/**
 * CloudFormation Configuration Routes
 * Provides real AWS resource configuration from CloudFormation stack outputs
 * Replaces hardcoded placeholder values with actual deployed resource identifiers
 */

const express = require('express');
const AWS = require('aws-sdk');

// Initialize AWS SDK
const cloudformation = new AWS.CloudFormation({ region: process.env.AWS_REGION || 'us-east-1' });

// Create Express router
const router = express.Router();

/**
 * Get CloudFormation stack outputs
 * GET /config/cloudformation?stackName=<stack-name>
 */
const getCloudFormationConfig = async (req, res) => {
  try {
    const { stackName } = req.query;
    
    if (!stackName) {
      return res.status(400).json({
        error: 'Stack name is required',
        message: 'Provide stackName query parameter'
      });
    }
    
    console.log(`📋 Fetching CloudFormation outputs for stack: ${stackName}`);
    
    // Get stack description with outputs
    const describeParams = {
      StackName: stackName
    };
    
    const stackResult = await cloudformation.describeStacks(describeParams).promise();
    
    if (!stackResult.Stacks || stackResult.Stacks.length === 0) {
      return res.status(404).json({
        error: 'Stack not found',
        message: `CloudFormation stack '${stackName}' does not exist`,
        stackName
      });
    }
    
    const stack = stackResult.Stacks[0];
    const outputs = stack.Outputs || [];
    
    // Transform outputs array to object for easier access
    const outputsMap = {};
    outputs.forEach(output => {
      outputsMap[output.OutputKey] = output.OutputValue;
    });
    
    // Extract real AWS resource identifiers
    const realConfig = {
      stackName,
      region: process.env.AWS_REGION || 'us-east-1',
      accountId: stack.StackId.split(':')[4], // Extract account ID from stack ARN
      stackStatus: stack.StackStatus,
      creationTime: stack.CreationTime,
      lastUpdatedTime: stack.LastUpdatedTime,
      
      // Real resource outputs from CloudFormation
      outputs: outputsMap,
      
      // Structured configuration for application use
      api: {
        gatewayUrl: outputsMap.ApiGatewayUrl,
        gatewayId: outputsMap.ApiGatewayId,
        stageName: outputsMap.ApiGatewayStageName,
        lambdaFunctionName: outputsMap.LambdaFunctionName,
        lambdaFunctionArn: outputsMap.LambdaFunctionArn
      },
      
      cognito: {
        userPoolId: outputsMap.UserPoolId,
        clientId: outputsMap.UserPoolClientId,
        domain: outputsMap.UserPoolDomain,
        region: process.env.AWS_REGION || 'us-east-1'
      },
      
      frontend: {
        bucketName: outputsMap.FrontendBucketName,
        cloudFrontId: outputsMap.CloudFrontDistributionId,
        websiteUrl: outputsMap.WebsiteURL
      },
      
      environment: {
        name: outputsMap.EnvironmentName,
        stackName: outputsMap.StackName
      }
    };
    
    console.log(`✅ CloudFormation configuration retrieved for ${stackName}`);
    
    res.json({
      success: true,
      ...realConfig,
      fetchedAt: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('❌ Error fetching CloudFormation configuration:', error);
    
    if (error.code === 'ValidationError') {
      return res.status(400).json({
        error: 'Invalid stack name',
        message: error.message,
        code: error.code
      });
    }
    
    if (error.code === 'AccessDenied') {
      return res.status(403).json({
        error: 'Access denied',
        message: 'Lambda function does not have permission to describe CloudFormation stacks',
        code: error.code
      });
    }
    
    res.status(500).json({
      error: 'Failed to fetch CloudFormation configuration',
      message: error.message,
      code: error.code || 'UNKNOWN_ERROR'
    });
  }
};

/**
 * List available CloudFormation stacks
 * GET /config/cloudformation/stacks
 */
const listCloudFormationStacks = async (req, res) => {
  try {
    console.log('📋 Listing CloudFormation stacks...');
    
    const params = {
      StackStatusFilter: [
        'CREATE_COMPLETE',
        'UPDATE_COMPLETE',
        'UPDATE_ROLLBACK_COMPLETE'
      ]
    };
    
    const result = await cloudformation.listStacks(params).promise();
    
    const stacks = result.StackSummaries.map(stack => ({
      stackName: stack.StackName,
      stackStatus: stack.StackStatus,
      creationTime: stack.CreationTime,
      lastUpdatedTime: stack.LastUpdatedTime,
      templateDescription: stack.TemplateDescription
    }));
    
    res.json({
      success: true,
      stacks,
      count: stacks.length,
      fetchedAt: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('❌ Error listing CloudFormation stacks:', error);
    
    res.status(500).json({
      error: 'Failed to list CloudFormation stacks',
      message: error.message,
      code: error.code || 'UNKNOWN_ERROR'
    });
  }
};

/**
 * Get current stack information (auto-detect from environment)
 * GET /config/cloudformation/current
 */
const getCurrentStackConfig = async (req, res) => {
  try {
    // Try to detect current stack name from environment or Lambda function name
    const currentStackName = process.env.STACK_NAME || 
                             process.env.AWS_LAMBDA_FUNCTION_NAME?.split('-').slice(0, -1).join('-') ||
                             'stocks-webapp-dev';
    
    console.log(`🔍 Auto-detecting current stack: ${currentStackName}`);
    
    // Redirect to the main CloudFormation config endpoint
    req.query.stackName = currentStackName;
    return await getCloudFormationConfig(req, res);
    
  } catch (error) {
    console.error('❌ Error getting current stack configuration:', error);
    
    res.status(500).json({
      error: 'Failed to get current stack configuration',
      message: error.message,
      suggestion: 'Try specifying the stack name explicitly'
    });
  }
};

/**
 * Validate CloudFormation configuration
 * GET /config/cloudformation/validate?stackName=<stack-name>
 */
const validateCloudFormationConfig = async (req, res) => {
  try {
    const { stackName } = req.query;
    
    if (!stackName) {
      return res.status(400).json({
        error: 'Stack name is required for validation'
      });
    }
    
    console.log(`🔍 Validating CloudFormation configuration for: ${stackName}`);
    
    // Get the configuration first
    const tempReq = { ...req };
    const tempRes = {
      json: (data) => data,
      status: (code) => ({ json: (data) => ({ statusCode: code, ...data }) })
    };
    
    const configResult = await getCloudFormationConfig(tempReq, tempRes);
    
    if (configResult.statusCode && configResult.statusCode !== 200) {
      return res.status(configResult.statusCode).json(configResult);
    }
    
    // Validate required outputs
    const validation = {
      isValid: true,
      issues: [],
      warnings: [],
      critical: []
    };
    
    // Check for required outputs
    const requiredOutputs = [
      'ApiGatewayUrl',
      'UserPoolId', 
      'UserPoolClientId',
      'FrontendBucketName'
    ];
    
    requiredOutputs.forEach(outputKey => {
      if (!configResult.outputs[outputKey]) {
        validation.issues.push(`Missing required output: ${outputKey}`);
        validation.isValid = false;
      }
    });
    
    // Check for placeholder or fake values
    const apiUrl = configResult.outputs.ApiGatewayUrl || '';
    if (apiUrl.includes('protrade.com') || apiUrl.includes('example.com') || apiUrl.includes('placeholder')) {
      validation.critical.push('API Gateway URL contains placeholder or fake domain');
      validation.isValid = false;
    }
    
    if (!apiUrl.includes('execute-api.amazonaws.com')) {
      validation.warnings.push('API Gateway URL does not follow AWS API Gateway format');
    }
    
    // Check Cognito configuration
    if (!configResult.cognito.userPoolId || !configResult.cognito.clientId) {
      validation.critical.push('Cognito configuration is incomplete');
      validation.isValid = false;
    }
    
    res.json({
      success: true,
      stackName,
      validation,
      config: configResult,
      validatedAt: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('❌ Error validating CloudFormation configuration:', error);
    
    res.status(500).json({
      error: 'Failed to validate CloudFormation configuration',
      message: error.message
    });
  }
};

// Define routes
router.get('/', getCloudFormationConfig);
router.get('/stacks', listCloudFormationStacks);
router.get('/current', getCurrentStackConfig);
router.get('/validate', validateCloudFormationConfig);

// Export router
module.exports = router;

// Also export individual functions for testing
module.exports.functions = {
  getCloudFormationConfig,
  listCloudFormationStacks,
  getCurrentStackConfig,
  validateCloudFormationConfig
};