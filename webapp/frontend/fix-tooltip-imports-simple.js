#!/usr/bin/env node

const fs = require('fs');
const { execSync } = require('child_process');

// List of files that need Tooltip imports based on the lint output
const filesToFix = [
  'src/components/HistoricalPriceChart.jsx',
  'src/components/ProfessionalChart.jsx',
  'src/components/admin/ConnectionMonitor.jsx',
  'src/components/admin/ProviderMetrics.jsx',
  'src/components/admin/RealTimeAnalytics.jsx',
  'src/pages/Dashboard.jsx',
  'src/pages/EconomicModeling.jsx',
  'src/pages/FinancialData.jsx',
  'src/pages/MetricsDashboard.jsx',
  'src/pages/OrderManagement.jsx',
  'src/pages/Portfolio.jsx',
  'src/pages/PortfolioHoldings.jsx',
  'src/pages/PortfolioPerformance.jsx',
  'src/pages/RealTimeDashboard.jsx',
  'src/pages/RiskManagement.jsx',
  'src/pages/ScoresDashboard.jsx',
  'src/pages/SectorAnalysis.jsx',
  'src/pages/SentimentAnalysis.jsx',
  'src/pages/ServiceHealth.jsx',
  'src/pages/SettingsApiKeys.jsx',
  'src/pages/StockDetail.jsx',
  'src/pages/StockExplorer.jsx',
  'src/pages/StockScreener.jsx',
  'src/pages/TechnicalHistory.jsx',
  'src/pages/TradingSignals.jsx',
];

function addMuiTooltip(filePath) {
  const content = fs.readFileSync(filePath, 'utf8');
  
  // Check if it uses MUI Tooltip
  if (!/<Tooltip/.test(content)) {
    return false;
  }
  
  // Check if Tooltip is already imported from MUI
  const muiImportMatch = content.match(/import\s*{[^}]*}\s*from\s*"@mui\/material"/);
  if (!muiImportMatch) {
    console.log(`⚠️ No MUI import found in ${filePath}`);
    return false;
  }
  
  const muiImportStr = muiImportMatch[0];
  if (muiImportStr.includes('Tooltip')) {
    console.log(`✅ ${filePath} already has Tooltip imported`);
    return false;
  }
  
  // Add Tooltip to the MUI import
  const newMuiImportStr = muiImportStr.replace(
    /(\s*)([^,\s}]+),(\s*)} from "@mui\/material"/,
    '$1$2,$1Tooltip,$3} from "@mui/material"'
  );
  
  const newContent = content.replace(muiImportStr, newMuiImportStr);
  
  if (newContent !== content) {
    fs.writeFileSync(filePath, newContent);
    console.log(`✅ Added Tooltip import to ${filePath}`);
    return true;
  }
  
  return false;
}

function addRechartsTooltip(filePath) {
  const content = fs.readFileSync(filePath, 'utf8');
  
  // Check if it uses RechartsTooltip or ChartTooltip
  const needsRechartsTooltip = /<RechartsTooltip/.test(content);
  const needsChartTooltip = /<ChartTooltip/.test(content);
  
  if (!needsRechartsTooltip && !needsChartTooltip) {
    return false;
  }
  
  // Check if recharts import exists
  const rechartsImportMatch = content.match(/import\s*{[^}]*}\s*from\s*"recharts"/);
  if (!rechartsImportMatch) {
    console.log(`⚠️ No recharts import found in ${filePath}`);
    return false;
  }
  
  let rechartsImportStr = rechartsImportMatch[0];
  let modified = false;
  
  // Add RechartsTooltip if needed
  if (needsRechartsTooltip && !rechartsImportStr.includes('Tooltip as RechartsTooltip')) {
    rechartsImportStr = rechartsImportStr.replace(
      /(\s*)([^,\s}]+),(\s*)} from "recharts"/,
      '$1$2,$1Tooltip as RechartsTooltip,$3} from "recharts"'
    );
    modified = true;
  }
  
  // Add ChartTooltip if needed
  if (needsChartTooltip && !rechartsImportStr.includes('Tooltip as ChartTooltip')) {
    rechartsImportStr = rechartsImportStr.replace(
      /(\s*)([^,\s}]+),(\s*)} from "recharts"/,
      '$1$2,$1Tooltip as ChartTooltip,$3} from "recharts"'
    );
    modified = true;
  }
  
  if (modified) {
    const newContent = content.replace(rechartsImportMatch[0], rechartsImportStr);
    fs.writeFileSync(filePath, newContent);
    console.log(`✅ Added recharts Tooltip import to ${filePath}`);
    return true;
  }
  
  return false;
}

function main() {
  console.log('🔧 Fixing Tooltip imports in all affected files...');
  
  let fixedCount = 0;
  
  for (const file of filesToFix) {
    console.log(`\n📁 Processing ${file}...`);
    
    try {
      if (!fs.existsSync(file)) {
        console.log(`⚠️ File not found: ${file}`);
        continue;
      }
      
      const muiFixed = addMuiTooltip(file);
      const rechartsFixed = addRechartsTooltip(file);
      
      if (muiFixed || rechartsFixed) {
        fixedCount++;
      }
    } catch (error) {
      console.error(`❌ Error processing ${file}:`, error.message);
    }
  }
  
  console.log(`\n🎉 Fixed ${fixedCount} files`);
  
  console.log('\n🧪 Running lint to check progress...');
  try {
    execSync('npm run lint', { stdio: 'inherit' });
    console.log('✅ All issues resolved!');
  } catch (error) {
    console.log('⚠️ Some issues remain, checking progress...');
  }
}

if (require.main === module) {
  main();
}