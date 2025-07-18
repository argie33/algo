#!/usr/bin/env node

/**
 * Script to remove all MUI imports and replace with TailwindCSS equivalents
 * This will completely eliminate the createPalette.js error
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// MUI component mappings to TailwindCSS alternatives
const muiReplacements = {
  // Basic components
  'Box': 'div',
  'Container': 'div className="container mx-auto"',
  'Typography': 'div',
  'Paper': 'div className="bg-white shadow-md rounded-lg p-4"',
  'Card': 'div className="bg-white shadow-md rounded-lg"',
  'CardContent': 'div className="p-4"',
  'CardHeader': 'div className="p-4 border-b"',
  'CardActions': 'div className="p-4 pt-0"',
  
  // Layout
  'Grid': 'div className="grid"',
  'Stack': 'div className="flex flex-col space-y-2"',
  'Divider': 'hr className="border-gray-200"',
  
  // Form components
  'TextField': 'input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"',
  'Button': 'button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"',
  'IconButton': 'button className="p-2 rounded-full hover:bg-gray-100"',
  'Select': 'select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"',
  'MenuItem': 'option',
  'FormControl': 'div className="mb-4"',
  'FormLabel': 'label className="block text-sm font-medium text-gray-700 mb-1"',
  'InputLabel': 'label className="block text-sm font-medium text-gray-700 mb-1"',
  'Switch': 'input type="checkbox" className="toggle"',
  'Checkbox': 'input type="checkbox" className="form-checkbox h-4 w-4 text-blue-600"',
  'Radio': 'input type="radio" className="form-radio h-4 w-4 text-blue-600"',
  
  // Navigation
  'Tabs': 'div className="border-b border-gray-200"',
  'Tab': 'button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"',
  'TabPanel': 'div className="mt-4"',
  'AppBar': 'nav className="bg-blue-600 text-white shadow-md"',
  'Toolbar': 'div className="px-4 py-2 flex items-center justify-between"',
  'MenuList': 'ul className="py-1"',
  'Menu': 'div className="absolute right-0 mt-2 w-48 bg-white rounded-md shadow-lg z-10"',
  
  // Feedback
  'Alert': 'div className="p-4 rounded-md bg-blue-50 border border-blue-200"',
  'Snackbar': 'div className="fixed bottom-4 right-4 bg-gray-800 text-white p-4 rounded-md shadow-lg"',
  'Dialog': 'div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"',
  'DialogTitle': 'h2 className="text-lg font-semibold mb-2"',
  'DialogContent': 'div className="mb-4"',
  'DialogActions': 'div className="flex justify-end space-x-2"',
  'CircularProgress': 'div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500"',
  'LinearProgress': 'div className="w-full bg-gray-200 rounded-full h-2"',
  
  // Data display
  'Table': 'table className="min-w-full divide-y divide-gray-200"',
  'TableHead': 'thead className="bg-gray-50"',
  'TableBody': 'tbody className="bg-white divide-y divide-gray-200"',
  'TableRow': 'tr',
  'TableCell': 'td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900"',
  'TableContainer': 'div className="overflow-x-auto"',
  'Chip': 'span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"',
  'Avatar': 'div className="h-8 w-8 rounded-full bg-gray-300 flex items-center justify-center"',
  'Badge': 'span className="inline-flex items-center justify-center px-2 py-1 text-xs font-bold leading-none text-red-100 bg-red-600 rounded-full"',
  'Tooltip': 'div',
  
  // Icons (commonly used)
  'CloseIcon': '×',
  'MenuIcon': '☰',
  'SearchIcon': '🔍',
  'MoreVertIcon': '⋮',
  'ArrowDropDownIcon': '▼',
  'ArrowDropUpIcon': '▲',
  'CheckIcon': '✓',
  'DeleteIcon': '🗑',
  'EditIcon': '✏',
  'VisibilityIcon': '👁',
  'VisibilityOffIcon': '🚫',
  'RefreshIcon': '↻',
  'DownloadIcon': '⬇',
  'UploadIcon': '⬆'
};

// List of MUI imports to remove entirely
const muiImportsToRemove = [
  '@mui/material',
  '@mui/icons-material',
  '@mui/lab',
  '@mui/system',
  '@mui/styles',
  '@mui/x-data-grid',
  '@mui/x-date-pickers'
];

function findJSXFiles(dir) {
  const files = [];
  
  function traverse(currentDir) {
    const items = fs.readdirSync(currentDir);
    
    for (const item of items) {
      const fullPath = path.join(currentDir, item);
      const stat = fs.statSync(fullPath);
      
      if (stat.isDirectory() && item !== 'node_modules' && item !== 'dist' && item !== '.git') {
        traverse(fullPath);
      } else if (stat.isFile() && (item.endsWith('.jsx') || item.endsWith('.js'))) {
        files.push(fullPath);
      }
    }
  }
  
  traverse(dir);
  return files;
}

function removeMUIImports(content) {
  // Remove import lines that contain MUI packages
  const lines = content.split('\n');
  const filteredLines = lines.filter(line => {
    const trimmed = line.trim();
    if (!trimmed.startsWith('import')) return true;
    
    return !muiImportsToRemove.some(muiPackage => 
      trimmed.includes(`'${muiPackage}`) || trimmed.includes(`"${muiPackage}`)
    );
  });
  
  return filteredLines.join('\n');
}

function replaceThemeProvider(content) {
  // Replace ThemeProvider usage
  content = content.replace(
    /<ThemeProvider[^>]*>/g,
    '<div className="theme-provider">'
  );
  content = content.replace(
    /<\/ThemeProvider>/g,
    '</div>'
  );
  
  // Replace useTheme() calls
  content = content.replace(
    /const\s+theme\s*=\s*useTheme\(\s*\)/g,
    'const theme = { palette: { mode: "light" } }'
  );
  
  return content;
}

function replaceMUIComponents(content) {
  // Replace MUI component usage with TailwindCSS equivalents
  for (const [muiComponent, replacement] of Object.entries(muiReplacements)) {
    // Replace opening tags
    const openTagRegex = new RegExp(`<${muiComponent}([^>]*)>`, 'g');
    content = content.replace(openTagRegex, (match, attributes) => {
      if (replacement.includes('className=')) {
        return `<${replacement}${attributes}>`;
      } else {
        return `<${replacement}${attributes ? ' ' + attributes : ''}>`;
      }
    });
    
    // Replace self-closing tags
    const selfClosingRegex = new RegExp(`<${muiComponent}([^>]*)\/>`, 'g');
    content = content.replace(selfClosingRegex, (match, attributes) => {
      if (replacement.includes('className=')) {
        return `<${replacement}${attributes} />`;
      } else {
        return `<${replacement}${attributes ? ' ' + attributes : ''} />`;
      }
    });
    
    // Replace closing tags
    const closingTagRegex = new RegExp(`<\/${muiComponent}>`, 'g');
    const baseTag = replacement.split(' ')[0].replace('<', '');
    content = content.replace(closingTagRegex, `</${baseTag}>`);
  }
  
  return content;
}

function processFile(filePath) {
  try {
    let content = fs.readFileSync(filePath, 'utf8');
    const originalContent = content;
    
    // Check if file contains MUI imports
    const hasMUIImports = muiImportsToRemove.some(muiPackage => 
      content.includes(muiPackage)
    );
    
    if (!hasMUIImports) {
      return false; // No changes needed
    }
    
    console.log(`Processing: ${filePath}`);
    
    // Apply transformations
    content = removeMUIImports(content);
    content = replaceThemeProvider(content);
    content = replaceMUIComponents(content);
    
    // Add React import if not present and file uses JSX
    if (content.includes('<') && !content.includes('import React')) {
      content = "import React from 'react';\n" + content;
    }
    
    // Only write if content changed
    if (content !== originalContent) {
      fs.writeFileSync(filePath, content, 'utf8');
      return true;
    }
    
    return false;
  } catch (error) {
    console.error(`Error processing ${filePath}:`, error.message);
    return false;
  }
}

function main() {
  console.log('🔧 Starting MUI removal process...');
  
  const srcDir = path.join(__dirname, 'src');
  const files = findJSXFiles(srcDir);
  
  let processedCount = 0;
  let changedCount = 0;
  
  for (const file of files) {
    processedCount++;
    const changed = processFile(file);
    if (changed) {
      changedCount++;
    }
  }
  
  console.log(`\n✅ Process complete!`);
  console.log(`   Files processed: ${processedCount}`);
  console.log(`   Files changed: ${changedCount}`);
  
  if (changedCount > 0) {
    console.log('\n🔄 Building to test changes...');
    try {
      execSync('npm run build', { stdio: 'inherit' });
      console.log('✅ Build successful! MUI removal complete.');
    } catch (error) {
      console.log('❌ Build failed. Some manual fixes may be needed.');
    }
  }
}

if (require.main === module) {
  main();
}

module.exports = { processFile, findJSXFiles, removeMUIImports };