#!/usr/bin/env node

/**
 * Comprehensive Multi-Stack Dependency Analyzer
 * Replaces "super random" manual approach with systematic validation
 * Covers Python, Node.js, Docker, AWS CloudFormation across entire project
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

console.log('🔍 Comprehensive Multi-Stack Dependency Analysis');
console.log('==================================================');

const projectRoot = '/home/stocks/algo';
const issues = [];
const warnings = [];
const insights = [];

// 1. DISCOVER ALL DEPENDENCY FILES
console.log('📋 Phase 1: Discovering all dependency files...');

function findDependencyFiles() {
  try {
    const cmd = `find ${projectRoot} -name "package*.json" -o -name "requirements*.txt" -o -name "pyproject.toml" -o -name "Dockerfile*" -o -name "*.yml" -o -name "*.yaml" | grep -v node_modules`;
    const files = execSync(cmd, { encoding: 'utf8' }).trim().split('\n').filter(Boolean);
    
    const categorized = {
      nodejs: files.filter(f => f.includes('package')),
      python: files.filter(f => f.includes('requirements') || f.includes('pyproject')),
      docker: files.filter(f => f.includes('Dockerfile')),
      cloudformation: files.filter(f => f.includes('template-') || f.includes('.yml') || f.includes('.yaml'))
    };
    
    console.log(`📊 Found ${files.length} dependency files:`);
    console.log(`   Node.js: ${categorized.nodejs.length}`);
    console.log(`   Python: ${categorized.python.length}`);
    console.log(`   Docker: ${categorized.docker.length}`);
    console.log(`   CloudFormation: ${categorized.cloudformation.length}`);
    
    return categorized;
  } catch (e) {
    issues.push('Failed to discover dependency files: ' + e.message);
    return { nodejs: [], python: [], docker: [], cloudformation: [] };
  }
}

// 2. ANALYZE NODE.JS DEPENDENCIES
console.log('\n🔧 Phase 2: Analyzing Node.js dependencies...');

function analyzeNodeJS(files) {
  files.forEach(file => {
    try {
      if (!fs.existsSync(file)) return;
      
      const pkg = JSON.parse(fs.readFileSync(file, 'utf8'));
      const deps = { ...pkg.dependencies, ...pkg.devDependencies };
      
      console.log(`\n📦 ${path.relative(projectRoot, file)}:`);
      
      // React ecosystem compatibility
      if (deps.react && deps['react-dom']) {
        const reactVer = deps.react.replace(/[^\d\.]/g, '');
        const reactDomVer = deps['react-dom'].replace(/[^\d\.]/g, '');
        if (reactVer !== reactDomVer) {
          issues.push(`${file}: React/ReactDOM version mismatch (${reactVer} vs ${reactDomVer})`);
        }
      }
      
      // Check for react-is conflicts
      if (deps['@emotion/react']) {
        try {
          const basePath = path.dirname(file);
          const reactIsCheck = execSync(`cd ${basePath} && npm list react-is --depth=10 2>/dev/null || echo "none"`, { encoding: 'utf8' });
          if (reactIsCheck.includes('react-is@19.')) {
            issues.push(`${file}: Potential react-is@19.x conflict with @emotion/react`);
          }
        } catch (e) {
          warnings.push(`${file}: Could not check react-is dependency chain`);
        }
      }
      
      // Security vulnerabilities
      try {
        const basePath = path.dirname(file);
        const auditResult = execSync(`cd ${basePath} && npm audit --audit-level=high --json 2>/dev/null || echo "{}"`, { encoding: 'utf8' });
        const audit = JSON.parse(auditResult);
        if (audit.metadata && audit.metadata.vulnerabilities) {
          const vulns = audit.metadata.vulnerabilities;
          const total = vulns.high + vulns.critical;
          if (total > 0) {
            issues.push(`${file}: ${total} high/critical security vulnerabilities`);
          }
        }
      } catch (e) {
        warnings.push(`${file}: Could not run security audit`);
      }
      
      // Outdated dependencies
      if (Object.keys(deps).length > 0) {
        insights.push(`${file}: ${Object.keys(deps).length} total dependencies`);
      }
      
    } catch (e) {
      warnings.push(`${file}: Could not parse package.json - ${e.message}`);
    }
  });
}

// 3. ANALYZE PYTHON DEPENDENCIES
console.log('\n🐍 Phase 3: Analyzing Python dependencies...');

function analyzePython(files) {
  const pythonPackages = new Set();
  const versionConflicts = new Map();
  
  files.forEach(file => {
    try {
      if (!fs.existsSync(file)) return;
      
      const content = fs.readFileSync(file, 'utf8');
      const lines = content.split('\n').filter(line => line.trim() && !line.startsWith('#'));
      
      console.log(`\n🐍 ${path.relative(projectRoot, file)}: ${lines.length} packages`);
      
      lines.forEach(line => {
        const match = line.match(/^([^=<>!]+)([=<>!].*)?/);
        if (match) {
          const packageName = match[1].trim();
          const versionSpec = match[2] || '';
          
          pythonPackages.add(packageName);
          
          if (versionConflicts.has(packageName)) {
            const existing = versionConflicts.get(packageName);
            if (existing !== versionSpec) {
              issues.push(`Python version conflict: ${packageName} (${existing} vs ${versionSpec})`);
            }
          } else {
            versionConflicts.set(packageName, versionSpec);
          }
        }
      });
      
    } catch (e) {
      warnings.push(`${file}: Could not analyze Python requirements - ${e.message}`);
    }
  });
  
  insights.push(`Python: ${pythonPackages.size} unique packages across ${files.length} files`);
}

// 4. ANALYZE DOCKER DEPENDENCIES
console.log('\n🐳 Phase 4: Analyzing Docker dependencies...');

function analyzeDocker(files) {
  const baseImages = new Map();
  const pythonVersions = new Set();
  
  files.forEach(file => {
    try {
      if (!fs.existsSync(file)) return;
      
      const content = fs.readFileSync(file, 'utf8');
      const lines = content.split('\n');
      
      lines.forEach(line => {
        const fromMatch = line.match(/^FROM\s+(.+)/i);
        if (fromMatch) {
          const image = fromMatch[1].trim();
          baseImages.set(image, (baseImages.get(image) || 0) + 1);
          
          // Extract Python versions
          const pythonMatch = image.match(/python:(\d+\.\d+)/);
          if (pythonMatch) {
            pythonVersions.add(pythonMatch[1]);
          }
        }
        
        // Check for security issues
        if (line.includes('pip install') && !line.includes('--no-cache-dir')) {
          warnings.push(`${file}: pip install without --no-cache-dir (Docker layer size)`);
        }
      });
      
    } catch (e) {
      warnings.push(`${file}: Could not analyze Dockerfile - ${e.message}`);
    }
  });
  
  console.log(`\n🐳 Docker Analysis:`);
  console.log(`   Base images: ${baseImages.size} unique`);
  baseImages.forEach((count, image) => {
    console.log(`   ${image}: ${count} files`);
  });
  
  if (pythonVersions.size > 1) {
    issues.push(`Multiple Python versions in Docker: ${Array.from(pythonVersions).join(', ')}`);
  }
  
  insights.push(`Docker: ${files.length} Dockerfiles, ${pythonVersions.size} Python versions`);
}

// 5. ANALYZE CLOUDFORMATION DEPENDENCIES
console.log('\n☁️ Phase 5: Analyzing CloudFormation dependencies...');

function analyzeCloudFormation(files) {
  const resources = new Map();
  const parameters = new Set();
  
  files.forEach(file => {
    try {
      if (!fs.existsSync(file)) return;
      
      const content = fs.readFileSync(file, 'utf8');
      
      // Count resource types
      const resourceMatches = content.match(/Type:\s*AWS::[A-Za-z0-9:]+/g) || [];
      resourceMatches.forEach(match => {
        const type = match.replace('Type: ', '').trim();
        resources.set(type, (resources.get(type) || 0) + 1);
      });
      
      // Extract parameters
      const paramMatches = content.match(/Parameters:\s*\n([\s\S]*?)(?=\n[A-Z]|\n\n|$)/g) || [];
      paramMatches.forEach(match => {
        const params = match.match(/^\s+([A-Za-z][A-Za-z0-9]*)/gm) || [];
        params.forEach(param => parameters.add(param.trim()));
      });
      
      // Check for hardcoded values
      if (content.includes('123456789') || content.includes('password')) {
        warnings.push(`${file}: Potential hardcoded credentials`);
      }
      
    } catch (e) {
      warnings.push(`${file}: Could not analyze CloudFormation - ${e.message}`);
    }
  });
  
  console.log(`\n☁️ CloudFormation Analysis:`);
  console.log(`   Resource types: ${resources.size} unique`);
  console.log(`   Parameters: ${parameters.size} unique`);
  
  insights.push(`CloudFormation: ${files.length} templates, ${resources.size} resource types`);
}

// 6. CROSS-STACK COMPATIBILITY ANALYSIS
console.log('\n🔄 Phase 6: Cross-stack compatibility analysis...');

function analyzeCrossStack(categorized) {
  // Node.js vs Python runtime compatibility
  const nodeJsFiles = categorized.nodejs.filter(f => f.includes('webapp'));
  const pythonFiles = categorized.python.filter(f => f.includes('requirements'));
  
  if (nodeJsFiles.length > 0 && pythonFiles.length > 0) {
    insights.push(`Multi-runtime project: ${nodeJsFiles.length} Node.js + ${pythonFiles.length} Python components`);
  }
  
  // Docker base image consistency
  const dockerFiles = categorized.docker;
  const cloudFormationFiles = categorized.cloudformation;
  
  if (dockerFiles.length > 0 && cloudFormationFiles.length > 0) {
    insights.push(`Container orchestration: ${dockerFiles.length} Dockerfiles + ${cloudFormationFiles.length} CF templates`);
  }
}

// MAIN EXECUTION
async function runComprehensiveAnalysis() {
  try {
    const categorized = findDependencyFiles();
    
    if (categorized.nodejs.length > 0) {
      analyzeNodeJS(categorized.nodejs);
    }
    
    if (categorized.python.length > 0) {
      analyzePython(categorized.python);
    }
    
    if (categorized.docker.length > 0) {
      analyzeDocker(categorized.docker);
    }
    
    if (categorized.cloudformation.length > 0) {
      analyzeCloudFormation(categorized.cloudformation);
    }
    
    analyzeCrossStack(categorized);
    
    // RESULTS SUMMARY
    console.log('\n📊 Comprehensive Analysis Results');
    console.log('================================');
    
    if (issues.length > 0) {
      console.error('❌ Critical Issues Found:');
      issues.forEach(issue => console.error(`  - ${issue}`));
    }
    
    if (warnings.length > 0) {
      console.warn('\n⚠️ Warnings:');
      warnings.forEach(warning => console.warn(`  - ${warning}`));
    }
    
    if (insights.length > 0) {
      console.log('\n💡 Project Insights:');
      insights.forEach(insight => console.log(`  - ${insight}`));
    }
    
    if (issues.length === 0 && warnings.length === 0) {
      console.log('✅ No critical dependency issues found across all stacks');
    }
    
    const totalFiles = Object.values(categorized).flat().length;
    console.log(`\n📈 Analysis Coverage: ${totalFiles} dependency files across 4 technology stacks`);
    
    // Exit with appropriate code
    if (issues.length > 0) {
      console.log('\n💡 Run individual stack analyzers for detailed fixes');
      process.exit(1);
    } else {
      console.log('\n✅ Multi-stack dependency analysis complete');
      process.exit(0);
    }
    
  } catch (error) {
    console.error('❌ Analysis failed:', error.message);
    process.exit(1);
  }
}

runComprehensiveAnalysis();