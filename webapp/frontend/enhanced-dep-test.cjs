#!/usr/bin/env node

/**
 * Enhanced Dependency Test - Comprehensive React/Frontend Dependency Validation
 * Catches critical compatibility issues including react-is/hoist-non-react-statics
 */

const { execSync } = require('child_process');
const pkg = require('./package.json');

console.log('🔍 Enhanced Dependency Analysis');
console.log('================================');

const deps = { ...pkg.dependencies, ...pkg.devDependencies };
const issues = [];
const warnings = [];

// 1. Chart.js conflicts with React 18.3.1
const chartjs = Object.keys(deps).filter(d => 
  d.includes('chart.js') || d.includes('react-chartjs') || d === 'chart.js'
);
if (chartjs.length > 0) {
  issues.push(`Chart.js dependencies: ${chartjs.join(', ')} (conflict with React 18.3.1)`);
}

// 2. use-sync-external-store redundancy (built into React 18+)
if (deps['use-sync-external-store']) {
  issues.push('use-sync-external-store explicitly included (built into React 18+)');
}

try {
  const tree = execSync('npm list use-sync-external-store 2>/dev/null || true', { encoding: 'utf8' });
  if (tree.includes('use-sync-external-store@') && !tree.includes('(empty)')) {
    // Check if it's properly overridden
    if (tree.includes('overridden')) {
      console.log('ℹ️  use-sync-external-store found but overridden (acceptable)');
    } else {
      issues.push('use-sync-external-store detected in node_modules without override (built into React 18+)');
    }
  }
} catch (e) {
  // Ignore error
}

// 3. React/ReactDOM version mismatches
if (deps.react && deps['react-dom'] && deps.react !== deps['react-dom']) {
  issues.push(`React/ReactDOM version mismatch: ${deps.react} vs ${deps['react-dom']}`);
}

// 4. React Query compatibility
const reactQuery = deps['@tanstack/react-query'];
if (reactQuery && !reactQuery.startsWith('^4.') && !reactQuery.startsWith('^5.')) {
  warnings.push(`React Query ${reactQuery} version may have compatibility issues`);
}

// 5. Router conflicts
if (deps['react-router'] && deps['react-router-dom']) {
  issues.push('Both react-router and react-router-dom installed (use only react-router-dom)');
}

// 6. NEW: React-is compatibility analysis (CRITICAL)
console.log('🧪 Analyzing react-is compatibility...');
try {
  const reactIsTree = execSync('npm list react-is --depth=10 2>/dev/null || echo "none"', { encoding: 'utf8' });
  
  // Check for react-is v19+ with hoist-non-react-statics
  if (reactIsTree.includes('react-is@19.')) {
    const hoistTree = execSync('npm list hoist-non-react-statics --depth=10 2>/dev/null || echo "none"', { encoding: 'utf8' });
    if (hoistTree.includes('hoist-non-react-statics@')) {
      issues.push('🚨 CRITICAL: react-is@19.x incompatible with hoist-non-react-statics (causes React Context errors)');
      issues.push('   ↳ Fix: Add "react-is": "^18.3.1" to package.json overrides');
    }
  }
  
  // Check for mixed react-is versions
  const reactIsVersions = [...new Set(reactIsTree.match(/react-is@[\d\.]+/g) || [])];
  if (reactIsVersions.length > 1) {
    warnings.push(`Multiple react-is versions detected: ${reactIsVersions.join(', ')}`);
  }
  
  // Check @emotion/react dependency chain (common source of react-is issues)
  if (deps['@emotion/react']) {
    const emotionTree = execSync('npm list @emotion/react --depth=5 2>/dev/null || echo "none"', { encoding: 'utf8' });
    if (emotionTree.includes('hoist-non-react-statics') && reactIsTree.includes('react-is@19.')) {
      issues.push('🚨 @emotion/react → hoist-non-react-statics → react-is@19.x conflict detected');
    }
  }
} catch (e) {
  warnings.push('Could not analyze react-is dependency tree');
}

// 7. NEW: MUI compatibility analysis
console.log('🎨 Analyzing MUI compatibility...');
const muiDeps = Object.keys(deps).filter(d => d.startsWith('@mui/'));
if (muiDeps.length > 0) {
  const muiVersions = muiDeps.map(dep => `${dep}@${deps[dep]}`);
  
  // Check for MUI v5 with React 18 compatibility
  const muiCore = deps['@mui/material'];
  if (muiCore && !muiCore.startsWith('^5.')) {
    warnings.push(`MUI Material ${muiCore} may have React 18 compatibility issues (use v5+)`);
  }
  
  // Check for @mui/lab alpha versions
  const muiLab = deps['@mui/lab'];
  if (muiLab && muiLab.includes('alpha')) {
    warnings.push(`@mui/lab ${muiLab} is alpha - may be unstable`);
  }
}

// 8. NEW: Testing library compatibility
console.log('🧪 Analyzing testing library compatibility...');
const testingReact = deps['@testing-library/react'];
if (testingReact) {
  // Check for Testing Library v13+ for React 18
  const version = testingReact.replace(/[^\d\.]/g, '');
  const majorVersion = parseInt(version.split('.')[0]);
  if (majorVersion < 13) {
    issues.push(`@testing-library/react ${testingReact} incompatible with React 18 (use v13+)`);
  }
}

// 9. NEW: Vite and build tool compatibility
console.log('⚡ Analyzing build tool compatibility...');
if (deps.vite) {
  const viteVersion = deps.vite.replace(/[^\d\.]/g, '');
  const majorVersion = parseInt(viteVersion.split('.')[0]);
  if (majorVersion < 4) {
    warnings.push(`Vite ${deps.vite} may have React 18 compatibility issues (use v4+)`);
  }
}

// 10. NEW: Override validation
console.log('🔧 Validating package overrides...');
if (pkg.overrides) {
  const overrides = pkg.overrides;
  
  // Validate react-is override
  if (overrides['react-is']) {
    const reactIsOverride = overrides['react-is'];
    if (reactIsOverride.startsWith('^18.') || reactIsOverride.startsWith('18.')) {
      console.log(`✅ react-is override: ${reactIsOverride} (recommended for compatibility)`);
    } else {
      warnings.push(`react-is override ${reactIsOverride} may cause compatibility issues`);
    }
  }
  
  // Check for use-sync-external-store override
  if (overrides['use-sync-external-store'] === false) {
    console.log('✅ use-sync-external-store disabled (good for React 18+)');
  }
}

// 11. NEW: Critical runtime dependency validation
console.log('⚙️  Validating runtime dependencies...');
try {
  const packageLock = require('./package-lock.json');
  const lockDeps = packageLock.packages || {};
  
  // Find all react-is installations
  const reactIsInstalls = Object.keys(lockDeps).filter(p => p.includes('node_modules/react-is'));
  const versions = [...new Set(reactIsInstalls.map(p => lockDeps[p].version).filter(Boolean))];
  
  if (versions.length > 1) {
    warnings.push(`Multiple react-is versions in lock file: ${versions.join(', ')}`);
  }
  
  if (versions.some(v => v.startsWith('19.'))) {
    issues.push('🚨 react-is v19.x found in package-lock.json (may cause Runtime Context errors)');
  }
  
} catch (e) {
  warnings.push('Could not analyze package-lock.json for version conflicts');
}

// Results Summary
console.log('\n📊 Analysis Results');
console.log('==================');

if (issues.length > 0) {
  console.error('❌ Critical dependency issues found:');
  issues.forEach(issue => {
    if (issue.includes('🚨')) {
      console.error(`  🚨 ${issue.replace('🚨 CRITICAL: ', '').replace('🚨 ', '')}`);
    } else {
      console.error(`  - ${issue}`);
    }
  });
}

if (warnings.length > 0) {
  console.warn('\n⚠️  Warnings:');
  warnings.forEach(warning => console.warn(`  - ${warning}`));
}

if (issues.length === 0 && warnings.length === 0) {
  console.log('✅ No dependency conflicts found');
  console.log('✅ All compatibility checks passed');
}

// Exit with appropriate code
if (issues.length > 0) {
  console.log(`\n💡 Run 'npm run test:dep:fix' for automated fixes`);
  process.exit(1);
} else if (warnings.length > 0) {
  console.log('\n✅ No critical issues - warnings can be addressed later');
  process.exit(0);
} else {
  process.exit(0);
}