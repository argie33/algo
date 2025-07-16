#!/usr/bin/env node
/**
 * SYSTEMATIC DATABASE CONNECTION DIAGNOSTICS & FIX
 * This script identifies and resolves the persistent SSL connection reset issue
 */

const { Client } = require('pg');
const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');
const net = require('net');
const dns = require('dns').promises;

// Configure AWS SDK
const secretsManager = new SecretsManagerClient({
    region: process.env.AWS_REGION || 'us-east-1'
});

const log = (level, message, ...args) => {
    const timestamp = new Date().toISOString();
    console.log(`${timestamp} - ${level.toUpperCase()} - ${message}`, ...args);
};

async function getDbCredentials() {
    const secretArn = process.env.DB_SECRET_ARN;
    if (!secretArn) {
        throw new Error('DB_SECRET_ARN environment variable not set');
    }

    const command = new GetSecretValueCommand({ SecretId: secretArn });
    const response = await secretsManager.send(command);
    return JSON.parse(response.SecretString);
}

async function testTcpConnection(host, port, timeout = 10000) {
    return new Promise((resolve, reject) => {
        const socket = new net.Socket();
        const timer = setTimeout(() => {
            socket.destroy();
            reject(new Error(`TCP connection timeout after ${timeout}ms`));
        }, timeout);

        socket.connect(port, host, () => {
            clearTimeout(timer);
            socket.destroy();
            resolve(true);
        });

        socket.on('error', (error) => {
            clearTimeout(timer);
            socket.destroy();
            reject(error);
        });
    });
}

async function testPostgresConnection(config, description) {
    const client = new Client(config);
    const startTime = Date.now();
    
    try {
        await client.connect();
        const connectTime = Date.now() - startTime;
        
        // Test basic query
        const result = await client.query('SELECT current_database(), current_user, version()');
        const queryTime = Date.now() - startTime;
        
        log('info', `✅ ${description} - SUCCESS in ${connectTime}ms (query: ${queryTime - connectTime}ms)`);
        log('info', `   Database: ${result.rows[0].current_database}`);
        log('info', `   User: ${result.rows[0].current_user}`);
        log('info', `   Version: ${result.rows[0].version.split(' ')[0]}`);
        
        await client.end();
        return true;
    } catch (error) {
        const elapsed = Date.now() - startTime;
        log('error', `❌ ${description} - FAILED after ${elapsed}ms`);
        log('error', `   Error: ${error.message}`);
        log('error', `   Code: ${error.code}`);
        
        try {
            await client.end();
        } catch (closeError) {
            // Ignore close errors
        }
        return false;
    }
}

async function systematicDiagnosticAndFix() {
    log('info', '🚀 SYSTEMATIC DATABASE CONNECTION DIAGNOSTIC & FIX');
    log('info', '==================================================');
    
    try {
        // Step 1: Get database credentials
        log('info', '📋 Step 1: Database Configuration');
        const secret = await getDbCredentials();
        const baseConfig = {
            host: secret.host,
            port: parseInt(secret.port) || 5432,
            database: secret.dbname || 'postgres',
            user: secret.username,
            password: secret.password,
        };
        
        log('info', `   Host: ${baseConfig.host}`);
        log('info', `   Port: ${baseConfig.port}`);
        log('info', `   Database: ${baseConfig.database}`);
        log('info', `   User: ${baseConfig.user}`);
        
        // Step 2: DNS Resolution Test
        log('info', '🔍 Step 2: DNS Resolution');
        try {
            const addresses = await dns.lookup(baseConfig.host, { all: true });
            log('info', `   ✅ DNS Resolution: ${addresses.length} addresses found`);
            addresses.forEach((addr, i) => {
                log('info', `     ${i + 1}. ${addr.address} (${addr.family === 4 ? 'IPv4' : 'IPv6'})`);
            });
        } catch (dnsError) {
            log('error', `   ❌ DNS Resolution failed: ${dnsError.message}`);
            throw dnsError;
        }
        
        // Step 3: TCP Connectivity Test
        log('info', '🌐 Step 3: TCP Connectivity');
        try {
            await testTcpConnection(baseConfig.host, baseConfig.port, 15000);
            log('info', `   ✅ TCP connection to ${baseConfig.host}:${baseConfig.port} successful`);
        } catch (tcpError) {
            log('error', `   ❌ TCP connection failed: ${tcpError.message}`);
            log('error', '   DIAGNOSIS: Network connectivity issue - check security groups');
            throw tcpError;
        }
        
        // Step 4: PostgreSQL Connection Tests with Different SSL Configurations
        log('info', '🔐 Step 4: PostgreSQL Connection Tests');
        
        const connectionConfigs = [
            {
                config: { ...baseConfig, ssl: false },
                description: 'No SSL (Plain Connection)'
            },
            {
                config: { 
                    ...baseConfig, 
                    ssl: { 
                        require: false, 
                        rejectUnauthorized: false 
                    }
                },
                description: 'SSL Optional (Flexible)'
            },
            {
                config: { 
                    ...baseConfig, 
                    ssl: { 
                        require: false, 
                        rejectUnauthorized: false,
                        checkServerIdentity: false
                    }
                },
                description: 'SSL Optional (No Identity Check)'
            },
            {
                config: { 
                    ...baseConfig, 
                    ssl: { 
                        require: true, 
                        rejectUnauthorized: false 
                    }
                },
                description: 'SSL Required (No Certificate Validation)'
            }
        ];
        
        let successfulConfig = null;
        
        for (let i = 0; i < connectionConfigs.length; i++) {
            const { config, description } = connectionConfigs[i];
            log('info', `   🔄 Testing: ${description}`);
            
            const success = await testPostgresConnection(config, description);
            if (success) {
                successfulConfig = config;
                log('info', `   🎉 WORKING CONFIGURATION FOUND: ${description}`);
                break;
            }
        }
        
        if (!successfulConfig) {
            log('error', '❌ ALL CONNECTION CONFIGURATIONS FAILED');
            log('error', '');
            log('error', '🚨 SYSTEMATIC DIAGNOSIS:');
            log('error', '   1. ✅ DNS Resolution: Working');
            log('error', '   2. ✅ TCP Connectivity: Working (can reach host:port)');
            log('error', '   3. ❌ PostgreSQL SSL/Auth: FAILING');
            log('error', '');
            log('error', '🔧 LIKELY CAUSES:');
            log('error', '   • RDS instance configured to reject connections from this subnet');
            log('error', '   • PostgreSQL pg_hba.conf not allowing SSL connections');
            log('error', '   • Authentication method mismatch (md5 vs scram-sha-256)');
            log('error', '   • RDS parameter group SSL configuration issue');
            log('error', '   • Database user does not exist or lacks permissions');
            log('error', '');
            log('error', '🛠️  RECOMMENDED FIXES:');
            log('error', '   1. Check RDS parameter group: rds.force_ssl = 0');
            log('error', '   2. Verify database user exists and has permissions');
            log('error', '   3. Check RDS security group allows connections from ECS subnet');
            log('error', '   4. Verify VPC configuration allows ECS->RDS communication');
            
            throw new Error('All PostgreSQL connection attempts failed');
        }
        
        // Step 5: Apply Working Configuration
        log('info', '🎯 Step 5: Applying Working Configuration');
        log('info', `   Working SSL Config: ${JSON.stringify(successfulConfig.ssl)}`);
        
        // Write the working configuration to a file for use in the main script
        const workingConfigPath = '/tmp/working-db-config.json';
        require('fs').writeFileSync(workingConfigPath, JSON.stringify({
            ...successfulConfig,
            // Add timeout configurations
            connectionTimeoutMillis: 30000,
            query_timeout: 30000,
            statement_timeout: 30000,
            keepAlive: true,
            keepAliveInitialDelayMillis: 10000
        }, null, 2));
        
        log('info', `   ✅ Working configuration saved to: ${workingConfigPath}`);
        
        // Step 6: Test Database Schema Creation
        log('info', '🗄️  Step 6: Test Database Schema Operations');
        const client = new Client(successfulConfig);
        await client.connect();
        
        try {
            // Test schema operations
            await client.query('SELECT current_database()');
            log('info', '   ✅ Basic query test passed');
            
            await client.query('CREATE TABLE IF NOT EXISTS connection_test (id SERIAL PRIMARY KEY, test_time TIMESTAMP DEFAULT NOW())');
            log('info', '   ✅ Table creation test passed');
            
            await client.query('INSERT INTO connection_test DEFAULT VALUES');
            log('info', '   ✅ Insert operation test passed');
            
            const testResult = await client.query('SELECT COUNT(*) as count FROM connection_test');
            log('info', `   ✅ Query operation test passed (${testResult.rows[0].count} records)`);
            
            await client.query('DROP TABLE IF EXISTS connection_test');
            log('info', '   ✅ Drop table test passed');
            
        } finally {
            await client.end();
        }
        
        log('info', '');
        log('info', '🎉 SYSTEMATIC DIAGNOSIS COMPLETE - DATABASE CONNECTION WORKING!');
        log('info', '');
        log('info', '✅ SUMMARY:');
        log('info', `   • Working SSL Configuration: ${JSON.stringify(successfulConfig.ssl)}`);
        log('info', `   • Configuration saved to: ${workingConfigPath}`);
        log('info', '   • Database schema operations tested successfully');
        log('info', '');
        log('info', '📝 NEXT STEPS:');
        log('info', '   1. Update webapp-db-init.js with working SSL configuration');
        log('info', '   2. Update Lambda database.js with working SSL configuration');
        log('info', '   3. Commit and deploy the fix');
        
        return successfulConfig;
        
    } catch (error) {
        log('error', '❌ SYSTEMATIC DIAGNOSIS FAILED');
        log('error', `   Final Error: ${error.message}`);
        log('error', '');
        log('error', '🚨 CRITICAL INFRASTRUCTURE ISSUE DETECTED');
        log('error', '');
        log('error', '🔧 MANUAL INVESTIGATION REQUIRED:');
        log('error', '   • Check AWS RDS Console for instance status');
        log('error', '   • Verify ECS task subnet configuration');
        log('error', '   • Check security group rules (ECS -> RDS port 5432)');
        log('error', '   • Validate VPC routing and NAT gateway configuration');
        log('error', '   • Review RDS parameter group SSL settings');
        
        throw error;
    }
}

// Export for use in other scripts
module.exports = { systematicDiagnosticAndFix };

// Run if called directly
if (require.main === module) {
    systematicDiagnosticAndFix()
        .then((config) => {
            log('info', '✅ Diagnostic completed successfully');
            process.exit(0);
        })
        .catch((error) => {
            log('error', '❌ Diagnostic failed:', error.message);
            process.exit(1);
        });
}