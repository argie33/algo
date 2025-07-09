const { Client } = require('pg');
const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');

// Enhanced database connectivity testing utility
class DatabaseConnectivityTest {
    constructor() {
        this.secretsManager = new SecretsManagerClient({
            region: process.env.WEBAPP_AWS_REGION || 'us-east-1'
        });
        this.testResults = {
            timestamp: new Date().toISOString(),
            environment: process.env.NODE_ENV || 'unknown',
            tests: []
        };
    }

    log(message, data = null) {
        const logEntry = {
            timestamp: new Date().toISOString(),
            message,
            data
        };
        console.log(JSON.stringify(logEntry));
        return logEntry;
    }

    async addTest(testName, testFunction) {
        const startTime = Date.now();
        let result;
        
        try {
            this.log(`Starting test: ${testName}`);
            result = await testFunction();
            const duration = Date.now() - startTime;
            
            this.testResults.tests.push({
                name: testName,
                status: 'PASSED',
                duration,
                result,
                timestamp: new Date().toISOString()
            });
            
            this.log(`Test PASSED: ${testName}`, { duration, result });
            return { success: true, result };
        } catch (error) {
            const duration = Date.now() - startTime;
            
            this.testResults.tests.push({
                name: testName,
                status: 'FAILED',
                duration,
                error: error.message,
                stack: error.stack,
                timestamp: new Date().toISOString()
            });
            
            this.log(`Test FAILED: ${testName}`, { duration, error: error.message });
            return { success: false, error: error.message };
        }
    }

    async runComprehensiveTests() {
        this.log('🔍 Starting comprehensive database connectivity tests');

        // Test 1: Environment Variables Check
        await this.addTest('Environment Variables Check', async () => {
            const requiredEnvVars = [
                'DB_SECRET_ARN',
                'DB_ENDPOINT',
                'WEBAPP_AWS_REGION',
                'NODE_ENV'
            ];
            
            const envCheck = {};
            let missingVars = [];
            
            for (const envVar of requiredEnvVars) {
                const value = process.env[envVar];
                envCheck[envVar] = {
                    present: !!value,
                    value: value ? (envVar.includes('SECRET') ? '[REDACTED]' : value) : null
                };
                
                if (!value) {
                    missingVars.push(envVar);
                }
            }
            
            if (missingVars.length > 0) {
                throw new Error(`Missing required environment variables: ${missingVars.join(', ')}`);
            }
            
            return envCheck;
        });

        // Test 2: Secrets Manager Access
        await this.addTest('Secrets Manager Access', async () => {
            const secretArn = process.env.DB_SECRET_ARN;
            if (!secretArn) {
                throw new Error('DB_SECRET_ARN not set');
            }

            const command = new GetSecretValueCommand({ SecretId: secretArn });
            const response = await this.secretsManager.send(command);
            
            if (!response.SecretString) {
                throw new Error('Secret exists but SecretString is empty');
            }
            
            let secret;
            try {
                secret = JSON.parse(response.SecretString);
            } catch (e) {
                throw new Error('Secret string is not valid JSON');
            }
            
            const requiredSecretKeys = ['host', 'port', 'username', 'password', 'dbname'];
            const secretCheck = {};
            const missingKeys = [];
            
            for (const key of requiredSecretKeys) {
                secretCheck[key] = {
                    present: !!secret[key],
                    type: typeof secret[key],
                    value: key === 'password' ? '[REDACTED]' : secret[key]
                };
                
                if (!secret[key]) {
                    missingKeys.push(key);
                }
            }
            
            if (missingKeys.length > 0) {
                throw new Error(`Missing required secret keys: ${missingKeys.join(', ')}`);
            }
            
            return secretCheck;
        });

        // Test 3: Database Connection (Basic)
        await this.addTest('Database Connection (Basic)', async () => {
            const secret = await this.getDbCredentials();
            
            const config = {
                host: secret.host,
                port: parseInt(secret.port) || 5432,
                database: secret.dbname || 'postgres',
                user: secret.username,
                password: secret.password,
                ssl: { rejectUnauthorized: false },
                connectionTimeoutMillis: 10000,
                statement_timeout: 5000,
                query_timeout: 5000
            };
            
            const client = new Client(config);
            
            try {
                await client.connect();
                
                const result = await client.query('SELECT version(), current_database(), current_user, inet_server_addr(), inet_server_port()');
                
                return {
                    connected: true,
                    serverInfo: result.rows[0],
                    connectionConfig: {
                        host: config.host,
                        port: config.port,
                        database: config.database,
                        user: config.user,
                        ssl: config.ssl
                    }
                };
            } finally {
                await client.end();
            }
        });

        // Test 4: Database Tables Check
        await this.addTest('Database Tables Check', async () => {
            const secret = await this.getDbCredentials();
            const client = new Client({
                host: secret.host,
                port: parseInt(secret.port) || 5432,
                database: secret.dbname || 'postgres',
                user: secret.username,
                password: secret.password,
                ssl: { rejectUnauthorized: false },
                connectionTimeoutMillis: 10000
            });
            
            try {
                await client.connect();
                
                // Check for critical tables
                const tablesResult = await client.query(`
                    SELECT table_name, table_type 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    ORDER BY table_name
                `);
                
                const tables = tablesResult.rows;
                const criticalTables = ['stocks', 'prices', 'user_api_keys', 'portfolio_holdings'];
                const existingCriticalTables = tables.filter(t => criticalTables.includes(t.table_name));
                
                // Check table counts
                const tableCounts = {};
                for (const table of existingCriticalTables) {
                    const countResult = await client.query(`SELECT COUNT(*) as count FROM ${table.table_name}`);
                    tableCounts[table.table_name] = parseInt(countResult.rows[0].count);
                }
                
                return {
                    totalTables: tables.length,
                    allTables: tables.map(t => t.table_name),
                    criticalTables: existingCriticalTables.map(t => t.table_name),
                    missingCriticalTables: criticalTables.filter(ct => !existingCriticalTables.find(t => t.table_name === ct)),
                    tableCounts
                };
            } finally {
                await client.end();
            }
        });

        // Test 5: Database Query Performance
        await this.addTest('Database Query Performance', async () => {
            const secret = await this.getDbCredentials();
            const client = new Client({
                host: secret.host,
                port: parseInt(secret.port) || 5432,
                database: secret.dbname || 'postgres',
                user: secret.username,
                password: secret.password,
                ssl: { rejectUnauthorized: false },
                connectionTimeoutMillis: 10000
            });
            
            try {
                await client.connect();
                
                const queries = [
                    { name: 'Simple SELECT', query: 'SELECT 1 as test' },
                    { name: 'Current Time', query: 'SELECT NOW() as current_time' },
                    { name: 'Stocks Count', query: 'SELECT COUNT(*) as count FROM stocks' },
                    { name: 'Recent Prices', query: 'SELECT symbol, date, close_price FROM prices ORDER BY date DESC LIMIT 5' }
                ];
                
                const queryResults = {};
                
                for (const { name, query } of queries) {
                    const startTime = Date.now();
                    try {
                        const result = await client.query(query);
                        const duration = Date.now() - startTime;
                        queryResults[name] = {
                            success: true,
                            duration,
                            rowCount: result.rowCount,
                            sampleData: result.rows.slice(0, 2) // First 2 rows only
                        };
                    } catch (error) {
                        queryResults[name] = {
                            success: false,
                            duration: Date.now() - startTime,
                            error: error.message
                        };
                    }
                }
                
                return queryResults;
            } finally {
                await client.end();
            }
        });

        // Test 6: VPC and Network Connectivity
        await this.addTest('VPC and Network Connectivity', async () => {
            const secret = await this.getDbCredentials();
            
            // Test DNS resolution
            const dns = require('dns');
            const { promisify } = require('util');
            const lookup = promisify(dns.lookup);
            
            const dnsResult = await lookup(secret.host);
            
            // Test basic network connectivity
            const net = require('net');
            const testConnection = () => {
                return new Promise((resolve, reject) => {
                    const socket = new net.Socket();
                    const timeout = setTimeout(() => {
                        socket.destroy();
                        reject(new Error('Connection timeout'));
                    }, 5000);
                    
                    socket.connect(secret.port, secret.host, () => {
                        clearTimeout(timeout);
                        socket.destroy();
                        resolve(true);
                    });
                    
                    socket.on('error', (err) => {
                        clearTimeout(timeout);
                        reject(err);
                    });
                });
            };
            
            const networkConnectivity = await testConnection();
            
            return {
                dnsResolution: {
                    host: secret.host,
                    resolvedIP: dnsResult.address,
                    family: dnsResult.family
                },
                networkConnectivity: networkConnectivity,
                targetPort: secret.port
            };
        });

        this.log('✅ Comprehensive database connectivity tests completed');
        return this.testResults;
    }

    async getDbCredentials() {
        const secretArn = process.env.DB_SECRET_ARN;
        if (!secretArn) {
            throw new Error('DB_SECRET_ARN environment variable not set');
        }
        
        const command = new GetSecretValueCommand({ SecretId: secretArn });
        const response = await this.secretsManager.send(command);
        return JSON.parse(response.SecretString);
    }

    generateSummaryReport() {
        const passedTests = this.testResults.tests.filter(t => t.status === 'PASSED');
        const failedTests = this.testResults.tests.filter(t => t.status === 'FAILED');
        
        return {
            summary: {
                totalTests: this.testResults.tests.length,
                passed: passedTests.length,
                failed: failedTests.length,
                overallStatus: failedTests.length === 0 ? 'HEALTHY' : 'ISSUES_FOUND'
            },
            failedTests: failedTests.map(t => ({
                name: t.name,
                error: t.error,
                duration: t.duration
            })),
            totalDuration: this.testResults.tests.reduce((sum, t) => sum + t.duration, 0),
            timestamp: this.testResults.timestamp
        };
    }
}

module.exports = { DatabaseConnectivityTest };