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

// 6. ENHANCED: React-is compatibility analysis (CRITICAL for Context errors)
console.log('🧪 Analyzing react-is compatibility...');

// First check package.json overrides
const reactIsOverride = pkg.overrides?.['react-is'];
if (!reactIsOverride) {
  issues.push('🚨 CRITICAL: react-is override missing from package.json (required for React 18 Context compatibility)');
  issues.push('   ↳ Fix: Add "react-is": "^18.3.1" to package.json overrides');
} else if (reactIsOverride.includes('19.')) {
  issues.push('🚨 CRITICAL: react-is override set to v19.x (incompatible with hoist-non-react-statics - causes Context errors)');
  issues.push('   ↳ Fix: Change to "react-is": "^18.3.1" in package.json overrides');
}

try {
  const reactIsTree = execSync('npm list react-is --depth=10 2>/dev/null || echo "none"', { encoding: 'utf8' });
  
  // Check for react-is v19+ with hoist-non-react-statics (the exact error you encountered)
  if (reactIsTree.includes('react-is@19.')) {
    const hoistTree = execSync('npm list hoist-non-react-statics --depth=10 2>/dev/null || echo "none"', { encoding: 'utf8' });
    if (hoistTree.includes('hoist-non-react-statics@')) {
      issues.push('🚨 CRITICAL: react-is@19.x incompatible with hoist-non-react-statics (causes "Cannot set properties of undefined (setting \'ContextConsumer\')" error)');
      issues.push('   ↳ Fix: Ensure "react-is": "^18.3.1" override in package.json, delete package-lock.json and node_modules, then npm install');
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

// 7. ENHANCED: MUI compatibility analysis (based on official MUI compatibility matrix 2025)
console.log('🎨 Analyzing MUI compatibility...');
const muiDeps = Object.keys(deps).filter(d => d.startsWith('@mui/'));
if (muiDeps.length > 0) {
  const muiVersions = muiDeps.map(dep => `${dep}@${deps[dep]}`);
  
  // CRITICAL: Check for @mui/styles with React 18 (official incompatibility)
  const muiStyles = deps['@mui/styles'];
  if (muiStyles) {
    issues.push('🚨 CRITICAL: @mui/styles is not compatible with React 18 (peer dependency conflict)');
    issues.push('   ↳ Fix: Remove @mui/styles and use @emotion/styled or @mui/system instead');
  }
  
  // Check for MUI v5+ requirement for React 18 (official requirement)
  const muiCore = deps['@mui/material'];
  if (muiCore) {
    const version = muiCore.replace(/[^\d\.]/g, '');
    const majorVersion = parseInt(version.split('.')[0]);
    if (majorVersion < 5) {
      issues.push(`🚨 MUI Material ${muiCore} incompatible with React 18 (requires v5+ per official docs)`);
      issues.push('   ↳ Fix: Upgrade to @mui/material@^5.0.0 or higher');
    }
  }
  
  // Check for missing @emotion dependencies (MUI v5 requirement)
  const emotionReact = deps['@emotion/react'];
  const emotionStyled = deps['@emotion/styled'];
  if (muiCore && (!emotionReact || !emotionStyled)) {
    issues.push('MUI v5+ requires @emotion/react and @emotion/styled peer dependencies');
    issues.push('   ↳ Fix: npm install @emotion/react @emotion/styled');
  }
  
  // Check for @mui/lab alpha versions (stability warning)
  const muiLab = deps['@mui/lab'];
  if (muiLab && muiLab.includes('alpha')) {
    warnings.push(`@mui/lab ${muiLab} is alpha - may be unstable in production`);
  }
  
  // Check for major version mismatches across MUI packages
  const muiMajorVersions = new Set();
  muiDeps.forEach(dep => {
    const version = deps[dep].replace(/[^\d\.]/g, '');
    const major = parseInt(version.split('.')[0]);
    if (!isNaN(major)) muiMajorVersions.add(major);
  });
  if (muiMajorVersions.size > 1) {
    warnings.push(`Mixed MUI major versions detected: ${Array.from(muiMajorVersions).join(', ')} - may cause conflicts`);
  }
  
  // ENHANCED: Check for MUI X packages compatibility (official date pickers, data grid)
  const muiX = Object.keys(deps).filter(d => d.startsWith('@mui/x-'));
  if (muiX.length > 0) {
    const muiXVersions = new Set();
    muiX.forEach(dep => {
      const version = deps[dep].replace(/[^\d\.]/g, '');
      const major = parseInt(version.split('.')[0]);
      if (!isNaN(major)) muiXVersions.add(major);
    });
    
    // MUI X v6+ required for React 18 (official requirement)
    muiX.forEach(dep => {
      const version = deps[dep].replace(/[^\d\.]/g, '');
      const majorVersion = parseInt(version.split('.')[0]);
      if (majorVersion < 6) {
        issues.push(`🚨 ${dep} ${deps[dep]} incompatible with React 18 (requires v6+ per MUI docs)`);
        issues.push(`   ↳ Fix: Upgrade to ${dep}@^6.0.0 or higher`);
      }
    });
    
    // Check for MUI X version consistency
    if (muiXVersions.size > 1) {
      warnings.push(`Mixed MUI X versions detected: ${Array.from(muiXVersions).join(', ')} - should use consistent versions`);
    }
  }
  
  // ENHANCED: Check for deprecated MUI packages
  const deprecatedMuiPackages = ['@mui/styles', '@mui/lab/LoadingButton', '@mui/lab/TabContext'];
  deprecatedMuiPackages.forEach(pkg => {
    if (deps[pkg]) {
      issues.push(`🚨 DEPRECATED: ${pkg} is deprecated in React 18 ecosystem`);
      if (pkg === '@mui/styles') {
        issues.push('   ↳ Fix: Use @emotion/styled or @mui/system/styled');
      } else if (pkg.includes('LoadingButton')) {
        issues.push('   ↳ Fix: Use @mui/material/LoadingButton instead');
      } else if (pkg.includes('TabContext')) {
        issues.push('   ↳ Fix: Use @mui/material/Tabs components instead');
      }
    }
  });
}

// 8. ENHANCED: Testing library compatibility (React Testing Library official requirements)
console.log('🧪 Analyzing testing library compatibility...');

// React Testing Library React 18 requirements (official compatibility)
const testingReact = deps['@testing-library/react'];
if (testingReact) {
  const version = testingReact.replace(/[^\d\.]/g, '');
  const majorVersion = parseInt(version.split('.')[0]);
  if (majorVersion < 13) {
    issues.push(`🚨 @testing-library/react ${testingReact} incompatible with React 18 (requires v13+ per official docs)`);
    issues.push('   ↳ Fix: npm install @testing-library/react@^13.0.0');
  }
}

// Testing Library ecosystem consistency
const testingLibDeps = Object.keys(deps).filter(d => d.startsWith('@testing-library/'));
const testingVersions = new Map();
testingLibDeps.forEach(dep => {
  const version = deps[dep].replace(/[^\d\.]/g, '');
  const major = parseInt(version.split('.')[0]);
  if (!isNaN(major)) {
    testingVersions.set(dep, major);
  }
});

// Check for Jest DOM compatibility (official peer dependency)
const jestDom = deps['@testing-library/jest-dom'];
if (testingReact && !jestDom) {
  warnings.push('@testing-library/jest-dom recommended with @testing-library/react for better assertions');
  warnings.push('   ↳ Install: npm install --save-dev @testing-library/jest-dom');
}

// User Event compatibility with React Testing Library
const userEvent = deps['@testing-library/user-event'];
if (testingReact && userEvent) {
  const userEventVersion = userEvent.replace(/[^\d\.]/g, '');
  const userEventMajor = parseInt(userEventVersion.split('.')[0]);
  const reactTestingMajor = testingVersions.get('@testing-library/react');
  
  // React Testing Library v13+ requires User Event v14+
  if (reactTestingMajor >= 13 && userEventMajor < 14) {
    issues.push(`🚨 @testing-library/user-event ${userEvent} incompatible with @testing-library/react v${reactTestingMajor}`);
    issues.push('   ↳ Fix: npm install --save-dev @testing-library/user-event@^14.0.0');
  }
}

// 9. ENHANCED: Vite and build tool compatibility (official Vite React 18 support)
console.log('⚡ Analyzing build tool compatibility...');

// Vite React 18 official requirements
if (deps.vite) {
  const viteVersion = deps.vite.replace(/[^\d\.]/g, '');
  const majorVersion = parseInt(viteVersion.split('.')[0]);
  if (majorVersion < 4) {
    issues.push(`🚨 Vite ${deps.vite} has limited React 18 support (requires v4+ for full compatibility)`);
    issues.push('   ↳ Fix: npm install vite@^4.0.0 or higher');
  } else if (majorVersion >= 5) {
    console.log(`✅ Vite ${deps.vite} has excellent React 18 support`);
  }
}

// Vite React plugin compatibility
const viteReact = deps['@vitejs/plugin-react'] || deps['@vitejs/plugin-react-swc'];
if (deps.vite && !viteReact) {
  warnings.push('Vite React plugin missing - required for React development');
  warnings.push('   ↳ Install: npm install --save-dev @vitejs/plugin-react');
} else if (viteReact) {
  const pluginVersion = viteReact.replace(/[^\d\.]/g, '');
  const majorVersion = parseInt(pluginVersion.split('.')[0]);
  if (majorVersion < 4) {
    warnings.push(`@vitejs/plugin-react ${viteReact} may have React 18 compatibility issues (recommend v4+)`);
  }
}

// ESLint Vite integration
if (deps.vite && deps.eslint) {
  const eslintVite = deps['vite-plugin-eslint'] || deps['@nabla/vite-plugin-eslint'];
  if (!eslintVite) {
    warnings.push('Consider vite-plugin-eslint for development-time linting');
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

// 11. ENHANCED: Critical runtime dependency validation (comprehensive package-lock analysis)
console.log('⚙️  Validating runtime dependencies...');
try {
  const packageLock = require('./package-lock.json');
  const lockDeps = packageLock.packages || {};
  
  // Find all react-is installations with detailed analysis
  const reactIsInstalls = Object.keys(lockDeps).filter(p => p.includes('node_modules/react-is'));
  const reactIsVersions = [...new Set(reactIsInstalls.map(p => lockDeps[p].version).filter(Boolean))];
  
  if (reactIsVersions.length > 1) {
    warnings.push(`Multiple react-is versions in lock file: ${reactIsVersions.join(', ')}`);
    console.log('🔍 React-is version analysis:');
    reactIsInstalls.forEach(install => {
      const version = lockDeps[install].version;
      console.log(`   ${install} → ${version}`);
    });
  }
  
  if (reactIsVersions.some(v => v.startsWith('19.'))) {
    issues.push('🚨 react-is v19.x found in package-lock.json (WILL cause Runtime Context errors)');
    issues.push('   ↳ Fix: Delete package-lock.json and node_modules, then npm install');
  }
  
  // Validate hoist-non-react-statics versions
  const hoistInstalls = Object.keys(lockDeps).filter(p => p.includes('node_modules/hoist-non-react-statics'));
  const hoistVersions = [...new Set(hoistInstalls.map(p => lockDeps[p].version).filter(Boolean))];
  
  if (hoistVersions.length > 1) {
    warnings.push(`Multiple hoist-non-react-statics versions: ${hoistVersions.join(', ')}`);
  }
  
  // Check for use-sync-external-store installations (should be overridden)
  const useSyncInstalls = Object.keys(lockDeps).filter(p => p.includes('node_modules/use-sync-external-store'));
  if (useSyncInstalls.length > 0) {
    const useSyncVersions = [...new Set(useSyncInstalls.map(p => lockDeps[p].version).filter(Boolean))];
    
    // Check if properly overridden by running npm ls
    try {
      const lsOutput = execSync('npm ls use-sync-external-store', { encoding: 'utf8' });
      if (lsOutput.includes('overridden')) {
        console.log(`✅ use-sync-external-store found but properly overridden: ${useSyncVersions.join(', ')}`);
      } else {
        issues.push(`🚨 use-sync-external-store found but NOT overridden: ${useSyncVersions.join(', ')}`);
        issues.push('   ↳ Check package.json overrides: "use-sync-external-store": false');
      }
    } catch (e) {
      warnings.push(`use-sync-external-store detected in lock file: ${useSyncVersions.join(', ')} - verify override working`);
    }
  }
  
  // Validate @emotion packages consistency
  const emotionInstalls = Object.keys(lockDeps).filter(p => p.includes('node_modules/@emotion/'));
  const emotionVersions = new Map();
  emotionInstalls.forEach(install => {
    const packageName = install.split('node_modules/').pop();
    const version = lockDeps[install].version;
    if (!emotionVersions.has(packageName)) emotionVersions.set(packageName, new Set());
    emotionVersions.get(packageName).add(version);
  });
  
  emotionVersions.forEach((versions, packageName) => {
    if (versions.size > 1) {
      warnings.push(`Multiple ${packageName} versions: ${Array.from(versions).join(', ')}`);
    }
  });
  
} catch (e) {
  warnings.push('Could not analyze package-lock.json for version conflicts');
  console.log(`   Reason: ${e.message}`);
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
  console.error(`\n🚨 CRITICAL: ${issues.length} dependency issues found that WILL cause runtime errors!`);
  console.error('These must be fixed before deployment:\n');
  issues.forEach(issue => console.error(`  💥 ${issue}`));
  console.log(`\n💡 Run 'npm run dep:fix' for automated fixes`);
  console.log(`💡 Or manually add to package.json overrides: "react-is": "^18.3.1"`);
  process.exit(1);
} else if (warnings.length > 0) {
  console.log('\n⚠️  Warnings found but not critical for runtime');
  process.exit(0);
} else {
  console.log('✅ All dependency validations passed');
  process.exit(0);
}