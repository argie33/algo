/**
 * Network Diagnostic Utility
 * Provides network connectivity testing and troubleshooting
 */

const { spawn } = require('child_process');
const { promisify } = require('util');
const dns = require('dns');
const dnsLookup = promisify(dns.lookup);

class NetworkDiagnostic {
  constructor() {
    this.timeout = 5000; // 5 second timeout
  }

  /**
   * Test network connectivity to a host
   */
  async testConnectivity(host, port = 80) {
    const startTime = Date.now();
    
    try {
      // Test DNS resolution first
      const dnsResult = await this.testDnsResolution(host);
      
      // Test TCP connectivity
      const tcpResult = await this.testTcpConnection(host, port);
      
      const duration = Date.now() - startTime;
      
      return {
        success: dnsResult.success && tcpResult.success,
        host,
        port,
        duration,
        dns: dnsResult,
        tcp: tcpResult,
        timestamp: new Date().toISOString()
      };
    } catch (error) {
      const duration = Date.now() - startTime;
      return {
        success: false,
        host,
        port,
        duration,
        error: error.message,
        timestamp: new Date().toISOString()
      };
    }
  }

  /**
   * Test DNS resolution for a hostname
   */
  async testDnsResolution(hostname) {
    const startTime = Date.now();
    
    try {
      const result = await dnsLookup(hostname);
      const duration = Date.now() - startTime;
      
      return {
        success: true,
        hostname,
        ip: result.address,
        family: result.family,
        duration,
        timestamp: new Date().toISOString()
      };
    } catch (error) {
      const duration = Date.now() - startTime;
      return {
        success: false,
        hostname,
        error: error.message,
        code: error.code,
        duration,
        timestamp: new Date().toISOString()
      };
    }
  }

  /**
   * Test TCP connection to host:port
   */
  async testTcpConnection(host, port) {
    const startTime = Date.now();
    
    return new Promise((resolve) => {
      const net = require('net');
      const socket = new net.Socket();
      
      const timeout = setTimeout(() => {
        socket.destroy();
        const duration = Date.now() - startTime;
        resolve({
          success: false,
          host,
          port,
          error: 'Connection timeout',
          duration,
          timestamp: new Date().toISOString()
        });
      }, this.timeout);

      socket.connect(port, host, () => {
        clearTimeout(timeout);
        socket.end();
        const duration = Date.now() - startTime;
        resolve({
          success: true,
          host,
          port,
          duration,
          timestamp: new Date().toISOString()
        });
      });

      socket.on('error', (error) => {
        clearTimeout(timeout);
        const duration = Date.now() - startTime;
        resolve({
          success: false,
          host,
          port,
          error: error.message,
          code: error.code,
          duration,
          timestamp: new Date().toISOString()
        });
      });
    });
  }

  /**
   * Test ping to a host (if available)
   */
  async testPing(host, count = 3) {
    const startTime = Date.now();
    
    return new Promise((resolve) => {
      const isWindows = process.platform === 'win32';
      const pingCmd = isWindows ? 'ping' : 'ping';
      const pingArgs = isWindows ? ['-n', count.toString(), host] : ['-c', count.toString(), host];
      
      const ping = spawn(pingCmd, pingArgs);
      let output = '';
      let error = '';
      
      const timeout = setTimeout(() => {
        ping.kill();
        const duration = Date.now() - startTime;
        resolve({
          success: false,
          host,
          error: 'Ping timeout',
          duration,
          timestamp: new Date().toISOString()
        });
      }, this.timeout);

      ping.stdout.on('data', (data) => {
        output += data.toString();
      });

      ping.stderr.on('data', (data) => {
        error += data.toString();
      });

      ping.on('close', (code) => {
        clearTimeout(timeout);
        const duration = Date.now() - startTime;
        
        if (code === 0) {
          // Parse ping results
          const lines = output.split('\n');
          const stats = this.parsePingOutput(output, isWindows);
          
          resolve({
            success: true,
            host,
            count,
            duration,
            stats,
            output: output.trim(),
            timestamp: new Date().toISOString()
          });
        } else {
          resolve({
            success: false,
            host,
            count,
            duration,
            error: error.trim() || `Ping failed with exit code ${code}`,
            output: output.trim(),
            timestamp: new Date().toISOString()
          });
        }
      });

      ping.on('error', (err) => {
        clearTimeout(timeout);
        const duration = Date.now() - startTime;
        resolve({
          success: false,
          host,
          error: err.message,
          duration,
          timestamp: new Date().toISOString()
        });
      });
    });
  }

  /**
   * Parse ping output to extract statistics
   */
  parsePingOutput(output, isWindows) {
    const stats = {
      packetsTransmitted: 0,
      packetsReceived: 0,
      packetLoss: 0,
      avgTime: 0
    };

    try {
      if (isWindows) {
        // Windows ping output parsing
        const lossMatch = output.match(/\((\d+)% loss\)/);
        if (lossMatch) {
          stats.packetLoss = parseInt(lossMatch[1]);
        }
        
        const avgMatch = output.match(/Average = (\d+)ms/);
        if (avgMatch) {
          stats.avgTime = parseInt(avgMatch[1]);
        }
      } else {
        // Unix/Linux ping output parsing
        const statsMatch = output.match(/(\d+) packets transmitted, (\d+) .*received, (\d+(?:\.\d+)?)% packet loss/);
        if (statsMatch) {
          stats.packetsTransmitted = parseInt(statsMatch[1]);
          stats.packetsReceived = parseInt(statsMatch[2]);
          stats.packetLoss = parseFloat(statsMatch[3]);
        }
        
        const timeMatch = output.match(/= ([\d.]+)\/([\d.]+)\/([\d.]+)\/([\d.]+) ms/);
        if (timeMatch) {
          stats.avgTime = parseFloat(timeMatch[2]);
        }
      }
    } catch (error) {
      console.warn('Failed to parse ping output:', error.message);
    }

    return stats;
  }

  /**
   * Comprehensive network diagnostic test
   */
  async runComprehensiveDiagnostic(targets = []) {
    const defaultTargets = [
      { host: 'google.com', port: 80, name: 'Google HTTP' },
      { host: 'cloudflare.com', port: 443, name: 'Cloudflare HTTPS' },
      { host: '8.8.8.8', port: 53, name: 'Google DNS' },
      { host: 'amazonaws.com', port: 443, name: 'AWS HTTPS' }
    ];

    const testTargets = targets.length > 0 ? targets : defaultTargets;
    const results = [];

    for (const target of testTargets) {
      console.log(`Testing connectivity to ${target.name || target.host}:${target.port}`);
      const result = await this.testConnectivity(target.host, target.port);
      result.name = target.name || `${target.host}:${target.port}`;
      results.push(result);
    }

    // Summary statistics
    const successful = results.filter(r => r.success).length;
    const total = results.length;
    const successRate = total > 0 ? (successful / total) * 100 : 0;

    return {
      summary: {
        total,
        successful,
        failed: total - successful,
        successRate: Math.round(successRate * 100) / 100
      },
      results,
      timestamp: new Date().toISOString()
    };
  }

  /**
   * Test database connectivity specifically
   */
  async testDatabaseConnectivity(config) {
    const { host, port = 5432, database } = config;
    
    console.log(`Testing database connectivity to ${host}:${port}`);
    
    const connectivity = await this.testConnectivity(host, port);
    
    return {
      type: 'database',
      host,
      port,
      database,
      connectivity,
      recommendations: this.getDatabaseRecommendations(connectivity),
      timestamp: new Date().toISOString()
    };
  }

  /**
   * Get recommendations based on connectivity results
   */
  getDatabaseRecommendations(result) {
    const recommendations = [];

    if (!result.success) {
      if (result.dns && !result.dns.success) {
        recommendations.push('DNS resolution failed - check hostname spelling and DNS configuration');
      }
      
      if (result.tcp && !result.tcp.success) {
        if (result.tcp.code === 'ECONNREFUSED') {
          recommendations.push('Connection refused - database server may be down or not accepting connections');
          recommendations.push('Check if PostgreSQL service is running');
          recommendations.push('Verify port configuration (default: 5432)');
        } else if (result.tcp.code === 'ETIMEDOUT') {
          recommendations.push('Connection timeout - firewall or network issue');
          recommendations.push('Check security groups and firewall rules');
        } else if (result.tcp.code === 'EHOSTUNREACH') {
          recommendations.push('Host unreachable - network routing issue');
          recommendations.push('Check network connectivity and routing');
        }
      }
    } else {
      recommendations.push('Network connectivity successful');
      if (result.duration > 2000) {
        recommendations.push('High latency detected - consider network optimization');
      }
    }

    return recommendations;
  }
}

module.exports = NetworkDiagnostic;