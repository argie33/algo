#!/usr/bin/env node

/**
 * Automated Sensitive Data Exposure Fix Tool
 * Systematically finds and fixes console.log statements exposing sensitive data
 */

const fs = require('fs');
const path = require('path');

const CRITICAL_EXPOSURE_PATTERNS = [
    // AWS ARNs
    { pattern: /console\.log.*arn:aws:[a-zA-Z0-9-]+:[a-zA-Z0-9-]*:\d{12}:[a-zA-Z0-9-/:]+/g, severity: 'CRITICAL', type: 'AWS_ARN' },
    
    // Database configurations
    { pattern: /console\.log.*password.*:/gi, severity: 'CRITICAL', type: 'DATABASE_PASSWORD' },
    { pattern: /console\.log.*DB_PASSWORD/gi, severity: 'CRITICAL', type: 'DATABASE_PASSWORD' },
    { pattern: /console\.log.*host.*:/gi, severity: 'HIGH', type: 'DATABASE_HOST' },
    { pattern: /console\.log.*username.*:/gi, severity: 'HIGH', type: 'DATABASE_USERNAME' },
    
    // API Keys and tokens
    { pattern: /console\.log.*API_KEY/gi, severity: 'CRITICAL', type: 'API_KEY' },
    { pattern: /console\.log.*SECRET/gi, severity: 'HIGH', type: 'SECRET' },
    { pattern: /console\.log.*TOKEN/gi, severity: 'HIGH', type: 'TOKEN' },
    { pattern: /console\.log.*PRIVATE_KEY/gi, severity: 'CRITICAL', type: 'PRIVATE_KEY' },
    
    // JWT tokens (pattern matching)
    { pattern: /console\.log.*eyJ[A-Za-z0-9+/=]{100,}/g, severity: 'CRITICAL', type: 'JWT_TOKEN' },
    
    // Environment variable exposure
    { pattern: /console\.log.*process\.env/gi, severity: 'HIGH', type: 'ENV_VARS' },
    
    // User data
    { pattern: /console\.log.*email.*:/gi, severity: 'MEDIUM', type: 'EMAIL' },
    { pattern: /console\.log.*userId.*:/gi, severity: 'MEDIUM', type: 'USER_ID' },
    { pattern: /console\.log.*ssn.*:/gi, severity: 'CRITICAL', type: 'SSN' },
    
    // AWS Secrets Manager content
    { pattern: /console\.log.*SecretString/gi, severity: 'CRITICAL', type: 'SECRET_STRING' },
    { pattern: /console\.log.*SecretBinary/gi, severity: 'CRITICAL', type: 'SECRET_BINARY' }
];

/**
 * Find all JavaScript files in the project
 */
function findJavaScriptFiles(dir, exclude = []) {
    const files = [];
    const items = fs.readdirSync(dir);
    
    for (const item of items) {
        const fullPath = path.join(dir, item);
        const stat = fs.statSync(fullPath);
        
        if (stat.isDirectory()) {
            if (!exclude.includes(item) && !item.startsWith('.')) {
                files.push(...findJavaScriptFiles(fullPath, exclude));
            }
        } else if (item.endsWith('.js') || item.endsWith('.jsx')) {
            files.push(fullPath);
        }
    }
    
    return files;
}

/**
 * Analyze file for sensitive data exposure
 */
function analyzeFile(filePath) {
    const content = fs.readFileSync(filePath, 'utf8');
    const lines = content.split('\n');
    const findings = [];
    
    lines.forEach((line, index) => {
        // Skip if line doesn't contain console.log
        if (!line.includes('console.log') && !line.includes('console.error') && !line.includes('console.warn')) {
            return;
        }
        
        CRITICAL_EXPOSURE_PATTERNS.forEach(({ pattern, severity, type }) => {
            const matches = line.match(pattern);
            if (matches) {
                findings.push({
                    file: filePath,
                    line: index + 1,
                    content: line.trim(),
                    severity,
                    type,
                    matches: matches.length
                });
            }
        });
        
        // Generic console.log exposure check
        if (line.includes('console.log') || line.includes('console.error')) {
            // Check for potential sensitive data keywords
            const sensitiveKeywords = ['password', 'secret', 'key', 'token', 'credential', 'auth', 'private'];
            const lowerLine = line.toLowerCase();
            
            for (const keyword of sensitiveKeywords) {
                if (lowerLine.includes(keyword)) {
                    findings.push({
                        file: filePath,
                        line: index + 1,
                        content: line.trim(),
                        severity: 'MEDIUM',
                        type: 'POTENTIAL_SENSITIVE',
                        keyword
                    });
                    break;
                }
            }
        }
    });
    
    return findings;
}

/**
 * Generate fix recommendations
 */
function generateFixRecommendations(findings) {
    const recommendations = [];
    
    const criticalFiles = [...new Set(findings.filter(f => f.severity === 'CRITICAL').map(f => f.file))];
    const highFiles = [...new Set(findings.filter(f => f.severity === 'HIGH').map(f => f.file))];
    
    recommendations.push('## IMMEDIATE ACTION REQUIRED (CRITICAL)');
    if (criticalFiles.length > 0) {
        recommendations.push(`**${criticalFiles.length} files with CRITICAL sensitive data exposure:**`);
        criticalFiles.forEach(file => {
            const criticalFindings = findings.filter(f => f.file === file && f.severity === 'CRITICAL');
            recommendations.push(`- ${file}: ${criticalFindings.length} critical exposures`);
        });
    }
    
    recommendations.push('\n## HIGH PRIORITY');
    if (highFiles.length > 0) {
        recommendations.push(`**${highFiles.length} files with HIGH severity exposures:**`);
        highFiles.forEach(file => {
            const highFindings = findings.filter(f => f.file === file && f.severity === 'HIGH');
            recommendations.push(`- ${file}: ${highFindings.length} high severity exposures`);
        });
    }
    
    recommendations.push('\n## RECOMMENDED FIXES');
    recommendations.push('1. **Import SecureLogger**: Add `const { secureLogger } = require("./secureLogger");` to each file');
    recommendations.push('2. **Replace console.log**: Use `secureLogger.info()`, `secureLogger.error()`, etc.');
    recommendations.push('3. **Add context**: Include component and operation context for better debugging');
    recommendations.push('4. **Remove sensitive data**: Ensure no passwords, tokens, or keys are logged');
    
    return recommendations.join('\n');
}

/**
 * Main execution
 */
function main() {
    console.log('🔍 Scanning for sensitive data exposure in console.log statements...\n');
    
    const projectRoot = '/home/stocks/algo';
    const excludeDirs = ['node_modules', '.git', 'dist', 'build', 'coverage'];
    
    try {
        const files = findJavaScriptFiles(projectRoot, excludeDirs);
        console.log(`📂 Found ${files.length} JavaScript files to analyze\n`);
        
        let allFindings = [];
        let filesWithIssues = 0;
        
        for (const file of files) {
            try {
                const findings = analyzeFile(file);
                if (findings.length > 0) {
                    allFindings.push(...findings);
                    filesWithIssues++;
                }
            } catch (error) {
                console.warn(`⚠️  Could not analyze ${file}: ${error.message}`);
            }
        }
        
        // Generate summary report
        console.log('📊 SENSITIVE DATA EXPOSURE ANALYSIS REPORT');
        console.log('=' .repeat(60));
        
        const criticalCount = allFindings.filter(f => f.severity === 'CRITICAL').length;
        const highCount = allFindings.filter(f => f.severity === 'HIGH').length;
        const mediumCount = allFindings.filter(f => f.severity === 'MEDIUM').length;
        
        console.log(`\n🚨 CRITICAL exposures: ${criticalCount}`);
        console.log(`⚠️  HIGH severity: ${highCount}`);
        console.log(`ℹ️  MEDIUM severity: ${mediumCount}`);
        console.log(`📁 Files affected: ${filesWithIssues}/${files.length}`);
        
        // Show critical findings first
        const criticalFindings = allFindings.filter(f => f.severity === 'CRITICAL');
        if (criticalFindings.length > 0) {
            console.log('\n🚨 CRITICAL FINDINGS (IMMEDIATE FIX REQUIRED):');
            console.log('-'.repeat(60));
            
            criticalFindings.slice(0, 10).forEach(finding => {
                console.log(`❌ ${finding.file}:${finding.line}`);
                console.log(`   Type: ${finding.type}`);
                console.log(`   Code: ${finding.content.substring(0, 100)}${finding.content.length > 100 ? '...' : ''}`);
                console.log('');
            });
            
            if (criticalFindings.length > 10) {
                console.log(`... and ${criticalFindings.length - 10} more critical findings`);
            }
        }
        
        // Generate fix recommendations
        console.log('\n📋 FIX RECOMMENDATIONS');
        console.log('=' .repeat(60));
        console.log(generateFixRecommendations(allFindings));
        
        // Generate detailed report file
        const reportData = {
            summary: {
                totalFiles: files.length,
                filesWithIssues,
                totalFindings: allFindings.length,
                criticalCount,
                highCount,
                mediumCount,
                timestamp: new Date().toISOString()
            },
            findings: allFindings,
            recommendations: generateFixRecommendations(allFindings)
        };
        
        fs.writeFileSync(
            path.join(projectRoot, 'SENSITIVE_DATA_EXPOSURE_REPORT.json'),
            JSON.stringify(reportData, null, 2)
        );
        
        console.log('\n📄 Detailed report saved to: SENSITIVE_DATA_EXPOSURE_REPORT.json');
        
        if (criticalCount > 0) {
            console.log('\n🚨 CRITICAL ISSUES FOUND - IMMEDIATE ACTION REQUIRED');
            process.exit(1);
        } else if (highCount > 0) {
            console.log('\n⚠️  HIGH PRIORITY ISSUES FOUND - SHOULD BE FIXED SOON');
            process.exit(1);
        } else {
            console.log('\n✅ No critical security exposures found');
            process.exit(0);
        }
        
    } catch (error) {
        console.error('💥 Analysis failed:', error.message);
        process.exit(1);
    }
}

if (require.main === module) {
    main();
}

module.exports = { findJavaScriptFiles, analyzeFile, generateFixRecommendations };