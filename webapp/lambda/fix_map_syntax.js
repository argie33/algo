
const fs = require('fs');
const path = require('path');

// Function to fix map function syntax errors specifically
function fixMapSyntax(content) {
  // Fix map functions that end with }));
  // Should be }); for most cases where it's a simple map
  content = content.replace(/(\s+\}\)\);)\s*$/gm, (match) => {
    return match.replace('}));', '});');
  });
  
  // Fix specific patterns where map functions have extra parentheses
  content = content.replace(/\.map\(([^)]+)\s*=>\s*\(\{[\s\S]*?\}\)\);/g, (match) => {
    // Count opening and closing parens to determine if we have extra
    const openParens = (match.match(/\(/g) || []).length;
    const closeParens = (match.match(/\)/g) || []).length;
    
    if (openParens < closeParens) {
      // Remove one closing parenthesis before the semicolon
      return match.replace(/\)\);$/, ');');
    }
    return match;
  });
  
  return content;
}

// Process files with known map syntax issues
const routeFiles = [
  'stocks.js',
  'market.js', 
  'portfolio.js'
];

let _totalFixed = 0;
let filesModified = 0;

routeFiles.forEach(fileName => {
  const filePath = path.join(__dirname, 'routes', fileName);
  if (fs.existsSync(filePath)) {
    let content = fs.readFileSync(filePath, 'utf8');
    const originalContent = content;
    content = fixMapSyntax(content);
    
    if (content !== originalContent) {
      fs.writeFileSync(filePath, content);
      filesModified++;
      console.log(`✅ Fixed map syntax in routes/${fileName}`);
    }
  }
});

console.log(`\n📊 Summary: Fixed map syntax in ${filesModified} files`);
console.log('🎉 Map syntax fixes completed');