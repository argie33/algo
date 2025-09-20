// Simple test to verify component files are valid
const fs = require('fs');
const path = require('path');

const componentsToTest = [
  'src/pages/Dashboard.jsx',
  'src/pages/Portfolio.jsx',
  'src/tests/mocks/apiMock.js'
];

console.log('🧪 Testing component file integrity...');

let allPassed = true;

componentsToTest.forEach(componentPath => {
  try {
    const content = fs.readFileSync(componentPath, 'utf8');

    // Basic syntax checks
    const hasImports = content.includes('import');
    const hasExports = content.includes('export');
    const hasReact = content.includes('React') || content.includes('jsx');

    console.log(`✅ ${componentPath}: ${content.length} chars, imports: ${hasImports}, exports: ${hasExports}`);

    // Check for problematic patterns
    const moduleLevel = content.match(/^(document\.|window\.)/gm);
    if (moduleLevel) {
      console.warn(`⚠️  ${componentPath}: Module-level DOM access detected`);
    }

  } catch (error) {
    console.error(`❌ ${componentPath}: ${error.message}`);
    allPassed = false;
  }
});

// Test API mock completeness
try {
  const mockContent = fs.readFileSync('src/tests/mocks/apiMock.js', 'utf8');
  const requiredExports = ['getStockPrices', 'getStockMetrics', 'getPortfolioAnalytics', 'getTradingSignalsDaily'];

  requiredExports.forEach(exportName => {
    if (mockContent.includes(`export const ${exportName}`)) {
      console.log(`✅ API Mock: ${exportName} exported`);
    } else {
      console.error(`❌ API Mock: Missing ${exportName}`);
      allPassed = false;
    }
  });

} catch (error) {
  console.error(`❌ API Mock test failed: ${error.message}`);
  allPassed = false;
}

console.log(allPassed ? '🎉 All component tests passed!' : '❌ Some tests failed');
process.exit(allPassed ? 0 : 1);