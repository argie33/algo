#!/usr/bin/env node
/**
 * SQL Injection Security Audit Script
 * Scans the codebase for potential SQL injection vulnerabilities
 */

const fs = require('fs');
const path = require('path');

class SQLInjectionAuditor {
  constructor() {
    this.vulnerabilities = [];
    this.scanStats = {
      filesScanned: 0,
      vulnerabilitiesFound: 0,
      criticalIssues: 0,
      highRiskIssues: 0,
      mediumRiskIssues: 0,
      lowRiskIssues: 0
    };

    // Dangerous patterns to look for
    this.dangerousPatterns = [
      {
        name: 'String concatenation in SQL',
        pattern: /['"`]\s*\+\s*[^'"`]*\s*\+\s*['"`]/g,
        risk: 'HIGH',
        description: 'String concatenation in SQL queries'
      },
      {
        name: 'Template literal SQL with variables',
        pattern: /`[^`]*\$\{[^}]*\}[^`]*`/g,
        risk: 'HIGH',
        description: 'Template literals with variables in SQL'
      },
      {
        name: 'Direct process.env in SQL',
        pattern: /['"`][^'"`]*process\.env\.[^'"`]*['"`]/g,
        risk: 'MEDIUM',
        description: 'Direct process.env usage in SQL strings'
      },
      {
        name: 'Dynamic table/column names',
        pattern: /(FROM|UPDATE|INTO|JOIN)\s+\$\{[^}]*\}/gi,
        risk: 'CRITICAL',
        description: 'Dynamic table or column names in SQL'
      },
      {
        name: 'Unparameterized WHERE clauses',
        pattern: /WHERE\s+[^$]*\+/gi,
        risk: 'HIGH',
        description: 'WHERE clauses using string concatenation'
      },
      {
        name: 'SQL keywords in string concatenation',
        pattern: /(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER)\s*['"`]\s*\+/gi,
        risk: 'CRITICAL',
        description: 'SQL keywords in string concatenation'
      },
      {
        name: 'User input directly in SQL',
        pattern: /(req\.body|req\.query|req\.params)[^$]*['"`]/g,
        risk: 'HIGH',
        description: 'User input directly embedded in SQL strings'
      }
    ];

    // Safe patterns (these are OK)
    this.safePatterns = [
      /\$[0-9]+/g, // Parameterized queries ($1, $2, etc.)
      /\?/g,       // Question mark placeholders
      /execute_values/g, // PostgreSQL safe bulk insert
      /prepared_statement/g // Prepared statements
    ];
  }

  /**
   * Scan a file for SQL injection vulnerabilities
   */
  scanFile(filePath) {
    try {
      const content = fs.readFileSync(filePath, 'utf8');
      const relativePath = path.relative(process.cwd(), filePath);
      
      this.scanStats.filesScanned++;

      // Check for dangerous patterns
      for (const patternInfo of this.dangerousPatterns) {
        const matches = content.match(patternInfo.pattern);
        if (matches) {
          for (const match of matches) {
            // Check if this is actually dangerous (not a safe pattern)
            const isSafe = this.safePatterns.some(safePattern => 
              safePattern.test(match)
            );

            if (!isSafe) {
              const lineNumber = this.getLineNumber(content, match);
              const vulnerability = {
                file: relativePath,
                line: lineNumber,
                pattern: patternInfo.name,
                risk: patternInfo.risk,
                description: patternInfo.description,
                code: match.trim(),
                context: this.getContext(content, lineNumber)
              };

              this.vulnerabilities.push(vulnerability);
              this.scanStats.vulnerabilitiesFound++;
              
              // Update risk counters
              switch (patternInfo.risk) {
                case 'CRITICAL':
                  this.scanStats.criticalIssues++;
                  break;
                case 'HIGH':
                  this.scanStats.highRiskIssues++;
                  break;
                case 'MEDIUM':
                  this.scanStats.mediumRiskIssues++;
                  break;
                case 'LOW':
                  this.scanStats.lowRiskIssues++;
                  break;
              }
            }
          }
        }
      }
    } catch (error) {
      console.error(`❌ Error scanning file ${filePath}:`, error.message);
    }
  }

  /**
   * Get line number for a match in content
   */
  getLineNumber(content, match) {
    const index = content.indexOf(match);
    if (index === -1) return 1;
    
    return content.substring(0, index).split('\n').length;
  }

  /**
   * Get context around a line number
   */
  getContext(content, lineNumber) {
    const lines = content.split('\n');
    const start = Math.max(0, lineNumber - 3);
    const end = Math.min(lines.length, lineNumber + 2);
    
    return lines.slice(start, end).map((line, idx) => {
      const actualLine = start + idx + 1;
      const marker = actualLine === lineNumber ? '>>>' : '   ';
      return `${marker} ${actualLine}: ${line}`;
    }).join('\n');
  }

  /**
   * Recursively scan directory
   */
  scanDirectory(dirPath, extensions = ['.js', '.ts', '.jsx', '.tsx', '.py']) {
    try {
      const items = fs.readdirSync(dirPath);
      
      for (const item of items) {
        const fullPath = path.join(dirPath, item);
        const stat = fs.statSync(fullPath);
        
        if (stat.isDirectory()) {
          // Skip node_modules and other common directories
          if (!['node_modules', '.git', '.vscode', 'dist', 'build'].includes(item)) {
            this.scanDirectory(fullPath, extensions);
          }
        } else if (stat.isFile()) {
          const ext = path.extname(fullPath);
          if (extensions.includes(ext)) {
            this.scanFile(fullPath);
          }
        }
      }
    } catch (error) {
      console.error(`❌ Error scanning directory ${dirPath}:`, error.message);
    }
  }

  /**
   * Generate security report
   */
  generateReport() {
    console.log('\n🛡️  SQL INJECTION SECURITY AUDIT REPORT');
    console.log('=' .repeat(50));
    
    // Summary
    console.log('\n📊 SCAN SUMMARY:');
    console.log(`Files Scanned: ${this.scanStats.filesScanned}`);
    console.log(`Total Vulnerabilities: ${this.scanStats.vulnerabilitiesFound}`);
    console.log(`Critical Issues: ${this.scanStats.criticalIssues}`);
    console.log(`High Risk Issues: ${this.scanStats.highRiskIssues}`);
    console.log(`Medium Risk Issues: ${this.scanStats.mediumRiskIssues}`);
    console.log(`Low Risk Issues: ${this.scanStats.lowRiskIssues}`);

    // Overall risk assessment
    let overallRisk = 'LOW';
    if (this.scanStats.criticalIssues > 0) {
      overallRisk = 'CRITICAL';
    } else if (this.scanStats.highRiskIssues > 0) {
      overallRisk = 'HIGH';
    } else if (this.scanStats.mediumRiskIssues > 0) {
      overallRisk = 'MEDIUM';
    }

    console.log(`\n🚨 OVERALL RISK LEVEL: ${overallRisk}`);

    // Detailed vulnerabilities
    if (this.vulnerabilities.length > 0) {
      console.log('\n🔍 DETAILED VULNERABILITIES:');
      console.log('-' .repeat(50));

      // Group by risk level
      const grouped = this.vulnerabilities.reduce((acc, vuln) => {
        if (!acc[vuln.risk]) acc[vuln.risk] = [];
        acc[vuln.risk].push(vuln);
        return acc;
      }, {});

      for (const risk of ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']) {
        if (grouped[risk]) {
          console.log(`\n🚨 ${risk} RISK ISSUES (${grouped[risk].length}):`);
          
          grouped[risk].forEach((vuln, index) => {
            console.log(`\n${index + 1}. ${vuln.pattern}`);
            console.log(`   File: ${vuln.file}:${vuln.line}`);
            console.log(`   Description: ${vuln.description}`);
            console.log(`   Code: ${vuln.code.substring(0, 100)}${vuln.code.length > 100 ? '...' : ''}`);
            
            if (process.argv.includes('--verbose')) {
              console.log(`   Context:\n${vuln.context}`);
            }
          });
        }
      }
    } else {
      console.log('\n✅ NO SQL INJECTION VULNERABILITIES FOUND!');
    }

    // Recommendations
    console.log('\n💡 SECURITY RECOMMENDATIONS:');
    console.log('-' .repeat(30));
    console.log('1. Always use parameterized queries ($1, $2, etc.)');
    console.log('2. Never use string concatenation for SQL queries');
    console.log('3. Validate and sanitize all user inputs');
    console.log('4. Use whitelisting for dynamic table/column names');
    console.log('5. Implement SQL injection protection middleware');
    console.log('6. Regular security audits and code reviews');

    // Return result for programmatic use
    return {
      overallRisk,
      stats: this.scanStats,
      vulnerabilities: this.vulnerabilities
    };
  }

  /**
   * Generate JSON report
   */
  generateJSONReport() {
    return {
      timestamp: new Date().toISOString(),
      overallRisk: this.scanStats.criticalIssues > 0 ? 'CRITICAL' : 
                   this.scanStats.highRiskIssues > 0 ? 'HIGH' :
                   this.scanStats.mediumRiskIssues > 0 ? 'MEDIUM' : 'LOW',
      summary: this.scanStats,
      vulnerabilities: this.vulnerabilities
    };
  }
}

// Main execution
if (require.main === module) {
  const auditor = new SQLInjectionAuditor();
  
  // Scan webapp/lambda directory for JavaScript files
  const webappPath = path.join(__dirname, 'webapp', 'lambda');
  if (fs.existsSync(webappPath)) {
    console.log('🔍 Scanning webapp/lambda directory...');
    auditor.scanDirectory(webappPath, ['.js', '.jsx', '.ts', '.tsx']);
  }

  // Scan Python data loaders
  console.log('🔍 Scanning Python data loaders...');
  auditor.scanDirectory(__dirname, ['.py']);

  // Generate and display report
  const result = auditor.generateReport();

  // Save JSON report
  const jsonReport = auditor.generateJSONReport();
  fs.writeFileSync('sql-injection-audit-report.json', JSON.stringify(jsonReport, null, 2));
  console.log('\n📄 JSON report saved to: sql-injection-audit-report.json');

  // Exit with error code if vulnerabilities found
  process.exit(result.overallRisk === 'CRITICAL' || result.overallRisk === 'HIGH' ? 1 : 0);
}

module.exports = SQLInjectionAuditor;