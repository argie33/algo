#!/usr/bin/env node

/**
 * ECS Task Definition Diagnostic Script
 * 
 * Compares failing ECS task configurations with working ones
 * to identify why tasks show "Exit code: None"
 */

require('dotenv').config();
const { ECSClient, DescribeTaskDefinitionCommand, ListTaskDefinitionsCommand } = require('@aws-sdk/client-ecs');

// Configure AWS SDK
const ecsClient = new ECSClient({
    region: process.env.AWS_REGION || 'us-east-1'
});

const WORKING_TASK_FAMILIES = [
    'stocks-app-data-loader-daily',
    'stocks-app-data-loader-technicals',
    'stocks-app-data-loader-earnings'
];

const FAILING_TASK_FAMILIES = [
    'stocks-webapp-db-init',
    'stocks-app-data-loader-earnings-history'
];

async function compareTaskDefinitions() {
    console.log('🔍 ECS Task Definition Comparison');
    console.log('================================');
    console.log(`🌍 AWS Region: ${process.env.AWS_REGION || 'us-east-1'}`);
    
    try {
        // Get working task definitions
        console.log('\n📊 Analyzing working task definitions...');
        const workingTasks = {};
        
        for (const family of WORKING_TASK_FAMILIES) {
            try {
                const command = new DescribeTaskDefinitionCommand({ taskDefinition: family });
                const response = await ecsClient.send(command);
                workingTasks[family] = response.taskDefinition;
                console.log(`✅ ${family}: ${response.taskDefinition.revision}`);
            } catch (error) {
                console.log(`⚠️ ${family}: ${error.message}`);
            }
        }
        
        // Get failing task definitions
        console.log('\n🚨 Analyzing failing task definitions...');
        const failingTasks = {};
        
        for (const family of FAILING_TASK_FAMILIES) {
            try {
                const command = new DescribeTaskDefinitionCommand({ taskDefinition: family });
                const response = await ecsClient.send(command);
                failingTasks[family] = response.taskDefinition;
                console.log(`❌ ${family}: ${response.taskDefinition.revision}`);
            } catch (error) {
                console.log(`⚠️ ${family}: ${error.message}`);
            }
        }
        
        // Compare configurations
        console.log('\n🔄 Configuration comparison analysis...');
        
        if (Object.keys(workingTasks).length > 0 && Object.keys(failingTasks).length > 0) {
            const workingTask = Object.values(workingTasks)[0];
            const failingTask = Object.values(failingTasks)[0];
            
            console.log('\n📋 Network Configuration Comparison:');
            compareNetworkConfig(workingTask, failingTask);
            
            console.log('\n🏗️ Container Configuration Comparison:');
            compareContainerConfig(workingTask, failingTask);
            
            console.log('\n🔧 Resource Configuration Comparison:');
            compareResourceConfig(workingTask, failingTask);
            
            console.log('\n🌐 Environment Variables Comparison:');
            compareEnvironmentVars(workingTask, failingTask);
            
        } else {
            console.log('⚠️ Cannot compare - missing working or failing task definitions');
        }
        
    } catch (error) {
        console.error('❌ ECS analysis failed:', error.message);
        console.error('🔍 Error details:', {
            name: error.name,
            code: error.code,
            statusCode: error.$metadata?.httpStatusCode
        });
    }
}

function compareNetworkConfig(working, failing) {
    console.log('Working task network:', {
        networkMode: working.networkMode,
        requiresCompatibilities: working.requiresCompatibilities,
        platformVersion: working.platformVersion
    });
    
    console.log('Failing task network:', {
        networkMode: failing.networkMode,
        requiresCompatibilities: failing.requiresCompatibilities,
        platformVersion: failing.platformVersion
    });
    
    // Check for differences
    if (working.networkMode !== failing.networkMode) {
        console.log(`🚨 DIFFERENCE: Network mode (${working.networkMode} vs ${failing.networkMode})`);
    }
}

function compareContainerConfig(working, failing) {
    const workingContainer = working.containerDefinitions[0];
    const failingContainer = failing.containerDefinitions[0];
    
    console.log('Working container:', {
        image: workingContainer.image,
        essential: workingContainer.essential,
        logDriver: workingContainer.logConfiguration?.logDriver
    });
    
    console.log('Failing container:', {
        image: failingContainer.image,
        essential: failingContainer.essential,
        logDriver: failingContainer.logConfiguration?.logDriver
    });
    
    // Check for differences
    if (workingContainer.image !== failingContainer.image) {
        console.log(`🚨 DIFFERENCE: Container image`);
    }
}

function compareResourceConfig(working, failing) {
    console.log('Working resources:', {
        cpu: working.cpu,
        memory: working.memory,
        executionRoleArn: working.executionRoleArn?.split('/').pop(),
        taskRoleArn: working.taskRoleArn?.split('/').pop()
    });
    
    console.log('Failing resources:', {
        cpu: failing.cpu,
        memory: failing.memory,
        executionRoleArn: failing.executionRoleArn?.split('/').pop(),
        taskRoleArn: failing.taskRoleArn?.split('/').pop()
    });
    
    // Check for differences
    if (working.cpu !== failing.cpu) {
        console.log(`🚨 DIFFERENCE: CPU allocation (${working.cpu} vs ${failing.cpu})`);
    }
    if (working.memory !== failing.memory) {
        console.log(`🚨 DIFFERENCE: Memory allocation (${working.memory} vs ${failing.memory})`);
    }
}

function compareEnvironmentVars(working, failing) {
    const workingEnv = working.containerDefinitions[0].environment || [];
    const failingEnv = failing.containerDefinitions[0].environment || [];
    
    console.log(`Working env vars (${workingEnv.length}):`, 
        workingEnv.map(e => e.name).join(', '));
    
    console.log(`Failing env vars (${failingEnv.length}):`, 
        failingEnv.map(e => e.name).join(', '));
    
    // Check for missing environment variables
    const workingNames = new Set(workingEnv.map(e => e.name));
    const failingNames = new Set(failingEnv.map(e => e.name));
    
    const missingInFailing = [...workingNames].filter(name => !failingNames.has(name));
    const extraInFailing = [...failingNames].filter(name => !workingNames.has(name));
    
    if (missingInFailing.length > 0) {
        console.log(`🚨 Missing in failing task: ${missingInFailing.join(', ')}`);
    }
    if (extraInFailing.length > 0) {
        console.log(`ℹ️ Extra in failing task: ${extraInFailing.join(', ')}`);
    }
}

// Self-executing diagnostic
if (require.main === module) {
    compareTaskDefinitions()
        .then(() => {
            console.log('\n✅ ECS task comparison complete');
            process.exit(0);
        })
        .catch(error => {
            console.error('\n❌ ECS diagnostic script failed:', error.message);
            process.exit(1);
        });
}

module.exports = { compareTaskDefinitions };