#!/usr/bin/env node

/**
 * CloudFormation Stack Status Checker
 * 
 * Checks the status of all CloudFormation stacks and their outputs
 * to understand deployment state and find missing resources
 */

const { CloudFormationClient, DescribeStacksCommand, ListStacksCommand } = require('@aws-sdk/client-cloudformation');

// Configure AWS SDK
const cfClient = new CloudFormationClient({
    region: process.env.AWS_REGION || 'us-east-1'
});

async function checkCloudFormationStatus() {
    console.log('🔍 CloudFormation Stack Status Checker');
    console.log('=====================================');
    console.log(`🌍 AWS Region: ${process.env.AWS_REGION || 'us-east-1'}`);
    
    try {
        // List all stacks
        console.log('\n📋 Listing all CloudFormation stacks...');
        const listCommand = new ListStacksCommand({
            StackStatusFilter: [
                'CREATE_COMPLETE',
                'UPDATE_COMPLETE', 
                'CREATE_IN_PROGRESS',
                'UPDATE_IN_PROGRESS',
                'ROLLBACK_COMPLETE',
                'CREATE_FAILED',
                'UPDATE_FAILED'
            ]
        });
        
        const listResponse = await cfClient.send(listCommand);
        const stacks = listResponse.StackSummaries || [];
        
        console.log(`📊 Found ${stacks.length} stacks:`);
        stacks.forEach(stack => {
            console.log(`   ${stack.StackName}: ${stack.StackStatus} (${stack.CreationTime?.toISOString()})`);
        });
        
        // Check specific stacks we care about
        const targetStacks = [
            'stocks-app-stack',
            'stocks-webapp-dev', 
            'stocks-webapp-lambda',
            'stocks-core'
        ];
        
        console.log('\n🔍 Detailed analysis of target stacks...');
        
        for (const stackName of targetStacks) {
            try {
                const describeCommand = new DescribeStacksCommand({ StackName: stackName });
                const response = await cfClient.send(describeCommand);
                const stack = response.Stacks[0];
                
                console.log(`\n📋 Stack: ${stackName}`);
                console.log(`   Status: ${stack.StackStatus}`);
                console.log(`   Created: ${stack.CreationTime?.toISOString()}`);
                console.log(`   Updated: ${stack.LastUpdatedTime?.toISOString() || 'Never'}`);
                
                // Check outputs
                if (stack.Outputs && stack.Outputs.length > 0) {
                    console.log(`   📤 Outputs (${stack.Outputs.length}):`);
                    stack.Outputs.forEach(output => {
                        console.log(`      ${output.OutputKey}: ${output.OutputValue}`);
                    });
                } else {
                    console.log(`   📤 No outputs found`);
                }
                
                // Check parameters
                if (stack.Parameters && stack.Parameters.length > 0) {
                    console.log(`   📥 Parameters (${stack.Parameters.length}):`);
                    stack.Parameters.forEach(param => {
                        // Hide sensitive values
                        const value = param.ParameterKey.toLowerCase().includes('secret') || 
                                     param.ParameterKey.toLowerCase().includes('password') ? 
                                     '[HIDDEN]' : param.ParameterValue;
                        console.log(`      ${param.ParameterKey}: ${value}`);
                    });
                }
                
                // Check for specific outputs we need
                const neededOutputs = ['DBSecretArn', 'DatabaseSecretArn', 'UserPoolId', 'UserPoolClientId'];
                const foundOutputs = (stack.Outputs || []).filter(output => 
                    neededOutputs.some(needed => output.OutputKey.includes(needed) || needed.includes(output.OutputKey))
                );
                
                if (foundOutputs.length > 0) {
                    console.log(`   🎯 Found needed outputs: ${foundOutputs.map(o => o.OutputKey).join(', ')}`);
                } else {
                    console.log(`   ⚠️ Missing needed outputs: ${neededOutputs.join(', ')}`);
                }
                
            } catch (error) {
                if (error.name === 'ValidationError') {
                    console.log(`   ❌ Stack ${stackName} not found`);
                } else {
                    console.log(`   ❌ Error checking ${stackName}: ${error.message}`);
                }
            }
        }
        
    } catch (error) {
        console.error('❌ CloudFormation check failed:', error.message);
        console.error('🔍 Error details:', {
            name: error.name,
            code: error.code
        });
    }
}

// Self-executing diagnostic
if (require.main === module) {
    checkCloudFormationStatus()
        .then(() => {
            console.log('\n✅ CloudFormation status check complete');
            process.exit(0);
        })
        .catch(error => {
            console.error('\n❌ CloudFormation check script failed:', error.message);
            process.exit(1);
        });
}

module.exports = { checkCloudFormationStatus };