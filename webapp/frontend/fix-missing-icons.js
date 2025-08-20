#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

// Common icon mappings that are frequently missing
const iconMappings = {
  'CheckCircleIcon': 'CheckCircle',
  'TestIcon': 'BugReport', 
  'SettingsIcon': 'Settings',
  'ExpandMoreIcon': 'ExpandMore',
  'CloseIcon': 'Close',
  'SlackIcon': 'Message',
  'WebhookIcon': 'Webhook',
  'CheckIcon': 'Check',
  'ErrorIcon': 'Error',
  'NetworkIcon': 'NetworkCheck',
  'AddIcon': 'Add',
  'OptimizeIcon': 'Tune',
  'TrendingDownIcon': 'TrendingDown',
  'TrendingUpIcon': 'TrendingUp',
  'CompareIcon': 'Compare',
  'CostIcon': 'AttachMoney',
  'SpeedIcon': 'Speed',
  'ConfirmIcon': 'CheckCircle',
  'ResetIcon': 'VpnKey',
  'RegisterIcon': 'PersonAdd',
  'RechartsTooltip': 'Tooltip',
};

function fixIconImports(filePath) {
  try {
    let content = fs.readFileSync(filePath, 'utf8');
    let hasChanges = false;
    
    // Find existing @mui/icons-material import
    const importMatch = content.match(/import\s+\{([^}]+)\}\s+from\s+["']@mui\/icons-material["']/);
    
    if (importMatch) {
      const existingImports = importMatch[1].split(',').map(imp => imp.trim());
      const newImports = new Set(existingImports);
      
      // Check for missing icons and add them
      for (const [missingIcon, correctIcon] of Object.entries(iconMappings)) {
        if (content.includes(missingIcon) && !existingImports.some(imp => imp.includes(correctIcon))) {
          newImports.add(correctIcon);
          hasChanges = true;
          // Replace the usage in the code
          content = content.replace(new RegExp(missingIcon, 'g'), correctIcon);
        }
      }
      
      if (hasChanges) {
        // Update the import statement
        const newImportList = Array.from(newImports).join(',\n  ');
        const newImportStatement = `import {\n  ${newImportList}\n} from "@mui/icons-material";`;
        content = content.replace(/import\s+\{[^}]+\}\s+from\s+["']@mui\/icons-material["']/, newImportStatement);
      }
    }
    
    if (hasChanges) {
      fs.writeFileSync(filePath, content);
      console.log(`✅ Fixed icons in: ${filePath}`);
      return true;
    }
    return false;
  } catch (error) {
    console.error(`❌ Error processing ${filePath}:`, error.message);
    return false;
  }
}

function findAndFixFiles(dir) {
  const files = fs.readdirSync(dir);
  let totalFixed = 0;
  
  for (const file of files) {
    const filePath = path.join(dir, file);
    const stat = fs.statSync(filePath);
    
    if (stat.isDirectory() && !file.startsWith('.') && file !== 'node_modules') {
      totalFixed += findAndFixFiles(filePath);
    } else if (file.endsWith('.jsx') || file.endsWith('.js')) {
      if (fixIconImports(filePath)) {
        totalFixed++;
      }
    }
  }
  
  return totalFixed;
}

console.log('🔧 Fixing missing MUI icon imports...');
const totalFixed = findAndFixFiles('./src');
console.log(`\n🎉 Fixed icons in ${totalFixed} files`);