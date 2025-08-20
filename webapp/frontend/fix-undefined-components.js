#!/usr/bin/env node
/**
 * Fix undefined components by adding proper imports
 */

const fs = require('fs');

console.log('🔧 Fixing undefined components...');

const componentFixes = [
  // Auth components missing icons
  {
    file: 'src/components/auth/RegisterForm.jsx',
    missingComponents: ['RegisterIcon'],
    importFrom: '@mui/icons-material',
    aliasMap: { RegisterIcon: 'PersonAdd as RegisterIcon' }
  },
  {
    file: 'src/components/auth/ForgotPasswordForm.jsx', 
    missingComponents: ['ResetIcon'],
    importFrom: '@mui/icons-material',
    aliasMap: { ResetIcon: 'LockReset as ResetIcon' }
  },
  
  // Chart components using recharts
  {
    file: 'src/pages/CryptoAdvancedDashboard.jsx',
    missingComponents: ['RechartsBarChart', 'RechartsTooltip'],
    importFrom: 'recharts',
    aliasMap: { 
      RechartsBarChart: 'BarChart as RechartsBarChart',
      RechartsTooltip: 'Tooltip as RechartsTooltip'
    }
  },
  
  // Pages missing icons
  {
    file: 'src/pages/EarningsCalendar.jsx',
    missingComponents: ['NeutralIcon'],
    importFrom: '@mui/icons-material',
    aliasMap: { NeutralIcon: 'Remove as NeutralIcon' }
  },
  
  // Admin components
  {
    file: 'src/components/admin/LiveDataAdmin.jsx',
    missingComponents: ['TestIcon', 'ImportIcon'],
    importFrom: '@mui/icons-material',
    aliasMap: { 
      TestIcon: 'PlayCircle as TestIcon',
      ImportIcon: 'CloudUpload as ImportIcon'
    }
  },
  
  // Portfolio components  
  {
    file: 'src/pages/Portfolio.jsx',
    missingComponents: ['RechartsTooltip'],
    importFrom: 'recharts',
    aliasMap: { RechartsTooltip: 'Tooltip as RechartsTooltip' }
  },
  
  // More chart components
  {
    file: 'src/pages/TradeHistory.jsx', 
    missingComponents: ['RechartsAreaChart', 'RechartsBarChart', 'Area', 'AreaChart'],
    importFrom: 'recharts',
    aliasMap: { 
      RechartsAreaChart: 'AreaChart as RechartsAreaChart',
      RechartsBarChart: 'BarChart as RechartsBarChart',
      Area: 'Area',
      AreaChart: 'AreaChart'
    }
  }
];

componentFixes.forEach(({ file, missingComponents, importFrom, aliasMap }) => {
  if (!fs.existsSync(file)) return;
  
  try {
    let content = fs.readFileSync(file, 'utf8');
    let modified = false;
    
    // Check if any of the missing components are used in the file
    const usedComponents = missingComponents.filter(comp => 
      content.includes(`<${comp}`) || content.includes(`${comp}`)
    );
    
    if (usedComponents.length === 0) return;
    
    // Find existing import from the same source
    const importRegex = new RegExp(`import\\s*{([^}]+)}\\s*from\\s*['"]${importFrom.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}['"];`);
    const importMatch = content.match(importRegex);
    
    if (importMatch) {
      // Add to existing import
      const existingImports = importMatch[1].split(',').map(i => i.trim()).filter(i => i);
      const newImports = usedComponents.map(comp => aliasMap[comp] || comp);
      const allImports = [...new Set([...existingImports, ...newImports])];
      
      const newImportStatement = `import {\n  ${allImports.join(',\n  ')}\n} from "${importFrom}";`;
      content = content.replace(importMatch[0], newImportStatement);
      modified = true;
    } else {
      // Create new import
      const newImports = usedComponents.map(comp => aliasMap[comp] || comp);
      const newImportStatement = `import {\n  ${newImports.join(',\n  ')}\n} from "${importFrom}";\n`;
      
      // Insert after the last import statement
      const lastImportMatch = content.match(/^import.*from.*['"];$/gm);
      if (lastImportMatch) {
        const lastImport = lastImportMatch[lastImportMatch.length - 1];
        const insertIndex = content.indexOf(lastImport) + lastImport.length;
        content = content.slice(0, insertIndex) + '\n' + newImportStatement + content.slice(insertIndex);
        modified = true;
      }
    }
    
    if (modified) {
      fs.writeFileSync(file, content);
      console.log(`   ✅ Fixed undefined components in ${file}: ${usedComponents.join(', ')}`);
    }
  } catch (e) {
    console.log(`   ⚠️  Failed to fix ${file}:`, e.message);
  }
});

console.log('🎉 Undefined component fixes completed!');