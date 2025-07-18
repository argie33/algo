/**
 * Network Connectivity Diagnostic Tool
 * Tests ECS to RDS network connectivity and validates security groups
 */

const { exec } = require('child_process');
const util = require('util');
const execAsync = util.promisify(exec);

class NetworkDiagnostic {
    constructor() {
        this.dbHost = null;
        this.dbPort = 5432;
    }

    /**
     * Initialize diagnostic with database configuration
     */
    async initialize() {
        try {
            // Get database configuration
            const SecretsManagerDiagnostic = require('./secretsManagerDiagnostic');
            const diagnostic = new SecretsManagerDiagnostic();
            const secretArn = process.env.DB_SECRET_ARN;
            
            if (!secretArn) {
                throw new Error('DB_SECRET_ARN not configured');
            }
            
            const result = await diagnostic.diagnoseSecret(secretArn);
            if (!result.success) {
                throw new Error(`Failed to get DB config: ${result.error}`);
            }
            
            this.dbHost = result.config.host;
            this.dbPort = parseInt(result.config.port) || 5432;
            
            console.log(`🌐 Network diagnostic initialized for ${this.dbHost}:${this.dbPort}`);
            
        } catch (error) {
            console.error('❌ Failed to initialize network diagnostic:', error.message);
            throw error;
        }
    }

    /**
     * Test basic network connectivity using ping
     */
    async testPing() {
        const diagnosticId = Math.random().toString(36).substr(2, 9);
        console.log(`🏓 [${diagnosticId}] Testing ping connectivity to ${this.dbHost}...`);
        
        try {
            // Try ping with 3 packets and 5 second timeout
            const { stdout, stderr } = await execAsync(`ping -c 3 -W 5 ${this.dbHost}`);
            
            console.log(`✅ [${diagnosticId}] Ping successful to ${this.dbHost}`);
            console.log(`🏓 [${diagnosticId}] Ping output:`, stdout.split('\n').slice(-2).join(' ').trim());
            
            return {
                success: true,
                diagnosticId,
                host: this.dbHost,
                output: stdout,
                message: 'Ping connectivity successful'
            };
            
        } catch (error) {
            console.error(`❌ [${diagnosticId}] Ping failed to ${this.dbHost}:`, error.message);
            
            return {
                success: false,
                diagnosticId,
                host: this.dbHost,
                error: error.message,
                stderr: error.stderr,
                message: 'Ping connectivity failed'
            };
        }
    }

    /**
     * Test TCP connectivity to database port
     */
    async testTcpConnection() {
        const diagnosticId = Math.random().toString(36).substr(2, 9);
        console.log(`🔌 [${diagnosticId}] Testing TCP connectivity to ${this.dbHost}:${this.dbPort}...`);
        
        try {
            // Use nc (netcat) to test TCP connection with 10 second timeout
            const { stdout, stderr } = await execAsync(`timeout 10 nc -z -v ${this.dbHost} ${this.dbPort}`);
            
            console.log(`✅ [${diagnosticId}] TCP connection successful to ${this.dbHost}:${this.dbPort}`);
            
            return {
                success: true,
                diagnosticId,
                host: this.dbHost,
                port: this.dbPort,
                output: stdout,
                message: 'TCP connectivity successful'
            };
            
        } catch (error) {
            console.error(`❌ [${diagnosticId}] TCP connection failed to ${this.dbHost}:${this.dbPort}:`, error.message);
            
            return {
                success: false,
                diagnosticId,
                host: this.dbHost,
                port: this.dbPort,
                error: error.message,
                stderr: error.stderr,
                message: 'TCP connectivity failed'
            };
        }
    }

    /**
     * Test PostgreSQL protocol connectivity
     */
    async testPostgreSQLConnection() {
        const diagnosticId = Math.random().toString(36).substr(2, 9);
        console.log(`🐘 [${diagnosticId}] Testing PostgreSQL protocol connectivity...`);
        
        try {
            const database = require('./database');
            
            // Use a simple connection test
            const client = await database.getPool().connect();
            await client.query('SELECT version() as version, current_database() as db');
            client.release();
            
            console.log(`✅ [${diagnosticId}] PostgreSQL protocol connection successful`);
            
            return {
                success: true,
                diagnosticId,
                host: this.dbHost,
                port: this.dbPort,
                message: 'PostgreSQL protocol connectivity successful'
            };
            
        } catch (error) {
            console.error(`❌ [${diagnosticId}] PostgreSQL protocol connection failed:`, error.message);
            
            return {
                success: false,
                diagnosticId,
                host: this.dbHost,
                port: this.dbPort,
                error: error.message,
                message: 'PostgreSQL protocol connectivity failed'
            };
        }
    }

    /**
     * Get network interface information
     */
    async getNetworkInfo() {
        const diagnosticId = Math.random().toString(36).substr(2, 9);
        console.log(`🌐 [${diagnosticId}] Getting network interface information...`);
        
        try {
            const results = {};
            
            // Get IP configuration
            try {
                const { stdout: ipStdout } = await execAsync('ip addr show');
                results.interfaces = this.parseIpAddr(ipStdout);
            } catch (error) {
                results.interfaces = { error: 'ip command failed' };
            }
            
            // Get routing table
            try {
                const { stdout: routeStdout } = await execAsync('ip route');
                results.routes = routeStdout.split('\n').filter(line => line.trim());
            } catch (error) {
                results.routes = { error: 'route command failed' };
            }
            
            // Get DNS configuration
            try {
                const { stdout: dnsStdout } = await execAsync('cat /etc/resolv.conf');
                results.dns = dnsStdout.split('\n').filter(line => line.trim() && !line.startsWith('#'));
            } catch (error) {
                results.dns = { error: 'DNS config not available' };
            }
            
            console.log(`✅ [${diagnosticId}] Network info collected`);
            
            return {
                success: true,
                diagnosticId,
                networkInfo: results,
                message: 'Network information collected'
            };
            
        } catch (error) {
            console.error(`❌ [${diagnosticId}] Failed to get network info:`, error.message);
            
            return {
                success: false,
                diagnosticId,
                error: error.message,
                message: 'Failed to collect network information'
            };
        }
    }

    /**
     * Parse ip addr output to extract interface information
     */
    parseIpAddr(output) {
        const interfaces = {};
        const lines = output.split('\n');
        let currentInterface = null;
        
        for (const line of lines) {
            // Match interface line (e.g., "2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP>")
            const interfaceMatch = line.match(/^\d+:\s+(\w+):\s+<([^>]+)>/);
            if (interfaceMatch) {
                currentInterface = interfaceMatch[1];
                interfaces[currentInterface] = {
                    flags: interfaceMatch[2].split(','),
                    addresses: []
                };
                continue;
            }
            
            // Match IP address line (e.g., "    inet 10.0.1.46/24 brd 10.0.1.255 scope global eth0")
            if (currentInterface) {
                const inetMatch = line.match(/^\s+inet\s+([^\s]+)/);
                if (inetMatch) {
                    interfaces[currentInterface].addresses.push({
                        type: 'inet',
                        address: inetMatch[1]
                    });
                }
                
                const inet6Match = line.match(/^\s+inet6\s+([^\s]+)/);
                if (inet6Match) {
                    interfaces[currentInterface].addresses.push({
                        type: 'inet6',
                        address: inet6Match[1]
                    });
                }
            }
        }
        
        return interfaces;
    }

    /**
     * Comprehensive network connectivity test
     */
    async runComprehensiveTest() {
        const diagnosticId = Math.random().toString(36).substr(2, 9);
        console.log(`🌐 [${diagnosticId}] Starting comprehensive network connectivity test...`);
        
        const startTime = Date.now();
        const results = {
            diagnosticId,
            timestamp: new Date().toISOString(),
            target: {
                host: this.dbHost,
                port: this.dbPort
            },
            tests: {}
        };
        
        try {
            // Test 1: Network interfaces
            console.log(`🌐 [${diagnosticId}] Step 1: Network interface information...`);
            results.tests.networkInfo = await this.getNetworkInfo();
            
            // Test 2: Basic ping connectivity
            console.log(`🌐 [${diagnosticId}] Step 2: Ping connectivity...`);
            results.tests.ping = await this.testPing();
            
            // Test 3: TCP connectivity
            console.log(`🌐 [${diagnosticId}] Step 3: TCP port connectivity...`);
            results.tests.tcp = await this.testTcpConnection();
            
            // Test 4: PostgreSQL protocol
            console.log(`🌐 [${diagnosticId}] Step 4: PostgreSQL protocol connectivity...`);
            results.tests.postgresql = await this.testPostgreSQLConnection();
            
            // Overall assessment
            const allTests = Object.values(results.tests);
            const successfulTests = allTests.filter(test => test.success).length;
            const totalTests = allTests.length;
            
            results.summary = {
                successfulTests,
                totalTests,
                successRate: Math.round((successfulTests / totalTests) * 100),
                overallStatus: successfulTests === totalTests ? 'healthy' : 
                              successfulTests > totalTests / 2 ? 'degraded' : 'unhealthy'
            };
            
            results.duration = Date.now() - startTime;
            
            console.log(`🌐 [${diagnosticId}] Comprehensive test completed in ${results.duration}ms`);
            console.log(`🌐 [${diagnosticId}] Success rate: ${results.summary.successRate}% (${successfulTests}/${totalTests})`);
            
            return results;
            
        } catch (error) {
            results.error = error.message;
            results.duration = Date.now() - startTime;
            
            console.error(`❌ [${diagnosticId}] Comprehensive test failed after ${results.duration}ms:`, error.message);
            
            return results;
        }
    }
}

module.exports = NetworkDiagnostic;