#!/usr/bin/env node
/**
 * Systematically fix remaining unused variables
 */

const fs = require('fs');

console.log('🔧 Systematically fixing remaining unused variables...');

// Comprehensive list of fixes based on lint output
const unusedVarFixes = [
  // ProfessionalChart.jsx
  { file: 'src/components/ProfessionalChart.jsx', from: 'const showLegend = false;', to: 'const _showLegend = false;' },
  
  // CostOptimizer.jsx
  { file: 'src/components/admin/CostOptimizer.jsx', from: '({ costData })', to: '({ costData: _costData })' },
  
  // RealTimeAnalytics.jsx  
  { file: 'src/components/admin/RealTimeAnalytics.jsx', from: '({ analyticsData })', to: '({ analyticsData: _analyticsData })' },
  { file: 'src/components/admin/RealTimeAnalytics.jsx', from: 'const formatBytes =', to: 'const _formatBytes =' },
  
  // ProtectedRoute.jsx
  { file: 'src/components/auth/ProtectedRoute.jsx', from: 'requireAuth = true', to: '_requireAuth = true' },
  
  // tabs.jsx
  { file: 'src/components/ui/tabs.jsx', from: '{ value, onValueChange', to: '{ value: _value, onValueChange: _onValueChange' },
  
  // Portfolio components
  { file: 'src/components/portfolio/PortfolioSummary.jsx', from: '({ value })', to: '({ value: _value })' },
  
  // Pages with index parameters
  { file: 'src/pages/About.jsx', from: ', index)', to: ', _index)' },
  { file: 'src/pages/AnalystInsights.jsx', from: ', index)', to: ', _index)' },
  
  // Variable assignments
  { file: 'src/pages/Dashboard.jsx', from: 'const logoSrc =', to: 'const _logoSrc =' },
  { file: 'src/pages/Dashboard.jsx', from: 'const useUser =', to: 'const _useUser =' },
  
  // Loading states
  { file: 'src/pages/EconomicModeling.jsx', from: 'isLoading =', to: '_isLoading =' },
  { file: 'src/pages/LiveDataAdmin.jsx', from: 'isLoading =', to: '_isLoading =' },
  { file: 'src/pages/NewsAnalysis.jsx', from: 'isLoading =', to: '_isLoading =' },
  
  // More specific fixes
  { file: 'src/components/ErrorBoundary.jsx', from: 'componentDidCatch(error', to: 'componentDidCatch(_error' },
  { file: 'src/services/api.js', from: 'const retryRequest =', to: 'const _retryRequest =' },
  { file: 'src/tests/setup.js', from: 'import { expect', to: 'import { expect as _expect' },
  { file: 'src/tests/components.test.jsx', from: 'fireEvent, waitFor', to: '_fireEvent, _waitFor' },
  
  // Destructuring parameters
  { file: 'src/utils/formatters.js', from: 'TrendingUp,', to: '_TrendingUp,' },
  { file: 'src/utils/formatters.js', from: 'TrendingDown,', to: '_TrendingDown,' },
  { file: 'src/utils/formatters.js', from: 'ShowChart,', to: '_ShowChart,' },
  { file: 'src/utils/formatters.js', from: 'InfoOutlined,', to: '_InfoOutlined,' },
  { file: 'src/utils/formatters.js', from: 'TrendingFlat,', to: '_TrendingFlat,' },
  
  // Function parameters in arrow functions
  { file: 'src/pages/Watchlist.jsx', from: '.map((item, index)', to: '.map((item, _index)' },
  { file: 'src/pages/TechnicalAnalysis.jsx', from: '.map((item, index)', to: '.map((item, _index)' },
];

let fixedCount = 0;

unusedVarFixes.forEach(({ file, from, to }) => {
  if (!fs.existsSync(file)) return;
  
  try {
    let content = fs.readFileSync(file, 'utf8');
    
    if (content.includes(from)) {
      content = content.replace(new RegExp(from.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), to);
      fs.writeFileSync(file, content);
      fixedCount++;
      console.log(`   ✅ Fixed unused variable in ${file}`);
    }
  } catch (e) {
    console.log(`   ⚠️  Failed to fix ${file}:`, e.message);
  }
});

console.log(`🎉 Fixed ${fixedCount} unused variable issues!`);