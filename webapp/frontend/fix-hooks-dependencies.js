#!/usr/bin/env node
/**
 * Fix React hooks dependency warnings
 */

const fs = require('fs');

console.log('🔧 Fixing React hooks dependency warnings...');

const hooksFixes = [
  // RealTimePriceWidget.jsx
  {
    file: 'src/components/RealTimePriceWidget.jsx',
    fixes: [
      {
        from: 'useEffect(() => {\n    fetchPriceData();\n  }, [symbol]);',
        to: 'useEffect(() => {\n    fetchPriceData();\n  }, [symbol, fetchPriceData]);'
      }
    ]
  },
  
  // LiveDataAdmin.jsx
  {
    file: 'src/components/admin/LiveDataAdmin.jsx',
    fixes: [
      {
        from: 'useEffect(() => {\n    fetchDashboardData();\n  }, []);',
        to: 'useEffect(() => {\n    fetchDashboardData();\n  }, [fetchDashboardData]);'
      }
    ]
  },
  
  // ErrorBoundary.jsx (ui version)
  {
    file: 'src/components/ui/ErrorBoundary.jsx',
    fixes: [
      {
        from: 'React.useEffect(() => {\n    logger.error(\n      \'ErrorBoundary caught error\',\n      { error, errorInfo: errorContext, component }\n    );\n  }, [error, errorInfo, component]);',
        to: 'React.useEffect(() => {\n    logger.error(\n      \'ErrorBoundary caught error\',\n      { error, errorInfo: errorContext, component }\n    );\n  }, [error, errorInfo, component, errorContext, logger]);'
      }
    ]
  },
  
  // AuthProvider.jsx
  {
    file: 'src/contexts/AuthProvider.jsx',
    fixes: [
      {
        from: 'useEffect(() => {\n    checkAuthState();\n  }, []);',
        to: 'useEffect(() => {\n    checkAuthState();\n  }, [checkAuthState]);'
      }
    ]
  },
  
  // Fix missing dependencies by adding them or using useCallback
  {
    file: 'src/components/RealTimePriceWidget.jsx',
    fixes: [
      {
        from: 'const fetchPriceData = async () => {',
        to: 'const fetchPriceData = useCallback(async () => {'
      },
      {
        from: '    } catch (error) {\n      console.error(\'Failed to fetch price data:\', error);\n      setError(\'Failed to load price data\');\n    }\n  };',
        to: '    } catch (error) {\n      console.error(\'Failed to fetch price data:\', error);\n      setError(\'Failed to load price data\');\n    }\n  }, [symbol]);'
      }
    ]
  }
];

hooksFixes.forEach(({ file, fixes }) => {
  if (!fs.existsSync(file)) return;
  
  try {
    let content = fs.readFileSync(file, 'utf8');
    let modified = false;
    
    fixes.forEach(({ from, to }) => {
      if (content.includes(from)) {
        content = content.replace(from, to);
        modified = true;
      }
    });
    
    // Add useCallback import if we added useCallback
    if (modified && content.includes('useCallback(') && !content.includes('useCallback')) {
      const importMatch = content.match(/import React, \{ ([^}]+) \} from ['"]react['"];/);
      if (importMatch) {
        const imports = importMatch[1].split(',').map(i => i.trim());
        if (!imports.includes('useCallback')) {
          imports.push('useCallback');
          const newImport = `import React, { ${imports.join(', ')} } from 'react';`;
          content = content.replace(importMatch[0], newImport);
        }
      }
    }
    
    if (modified) {
      fs.writeFileSync(file, content);
      console.log(`   ✅ Fixed hooks dependencies in ${file}`);
    }
  } catch (e) {
    console.log(`   ⚠️  Failed to fix ${file}:`, e.message);
  }
});

console.log('🎉 React hooks dependency fixes completed!');