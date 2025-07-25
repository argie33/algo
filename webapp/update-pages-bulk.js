#!/usr/bin/env node

/**
 * Bulk Page Update Script
 * Automatically adds error handling and DataContainer to all pages
 */

const fs = require('fs');
const path = require('path');

const PAGES_DIR = './frontend/src/pages';

// Common patterns to detect and replace
const PATTERNS = {
  // Import additions
  addImports: {
    pattern: /import { useSimpleFetch } from ['"]..\/hooks\/useSimpleFetch['"];?/,
    replacement: `import { useSimpleFetch } from '../hooks/useSimpleFetch';
import ApiErrorAlert from '../components/ApiErrorAlert';
import DataContainer from '../components/DataContainer';`
  },

  // useSimpleFetch calls that need DataContainer wrapping
  wrapApiCalls: {
    pattern: /const \{ data: (\w+), loading: (\w+), error: (\w+)(?:, refetch: (\w+))? \} = useSimpleFetch\(([^)]+)\);/g,
    replacement: (match, data, loading, error, refetch, url) => {
      const refetchVar = refetch || `${data}Refetch`;
      return `const { data: ${data}, loading: ${loading}, error: ${error}, refetch: ${refetchVar} } = useSimpleFetch(${url});`;
    }
  },

  // Component patterns that render data directly
  wrapComponents: {
    // Table components
    tablePattern: /<Table[^>]*>[\s\S]*?<\/Table>/g,
    // Card components with data
    cardPattern: /<Card[^>]*>[\s\S]*?{.*\.map\([\s\S]*?\)<\/Card>/g,
    // Grid components with data
    gridPattern: /<Grid[^>]*>[\s\S]*?{.*\.map\([\s\S]*?\)<\/Grid>/g
  }
};

// Data type mappings based on page name and API calls
const DATA_TYPE_MAPPING = {
  'Dashboard': 'stocks',
  'Portfolio': 'portfolio', 
  'StockDetail': 'stocks',
  'StockExplorer': 'stocks',
  'MarketOverview': 'stocks',
  'TradingSignals': 'trading_signals',
  'SentimentAnalysis': 'market_sentiment',
  'SectorAnalysis': 'sectors',
  'NewsAnalysis': 'news',
  'EarningsCalendar': 'calendar',
  'Watchlist': 'watchlist',
  'TradeHistory': 'activity',
  'ScoresDashboard': 'stocks'
};

// Get fallback data type from page name or content
function getFallbackDataType(filename, content) {
  const baseName = path.basename(filename, '.jsx');
  
  // Check mapping first
  if (DATA_TYPE_MAPPING[baseName]) {
    return DATA_TYPE_MAPPING[baseName];
  }
  
  // Detect from API calls
  if (content.includes('/api/stocks') || content.includes('/api/scores')) return 'stocks';
  if (content.includes('/api/portfolio')) return 'portfolio';
  if (content.includes('/api/trading') || content.includes('/api/signals')) return 'trading_signals';
  if (content.includes('/api/sentiment')) return 'market_sentiment';
  if (content.includes('/api/sectors')) return 'sectors';
  if (content.includes('/api/news')) return 'news';
  if (content.includes('/api/calendar')) return 'calendar';
  if (content.includes('/api/watchlist')) return 'watchlist';
  if (content.includes('/api/market')) return 'stocks';
  
  return 'stocks'; // default
}

// Extract component name from file
function getComponentName(filename) {
  return path.basename(filename, '.jsx');
}

// Update a single page file
function updatePageFile(filePath) {
  console.log(`📝 Updating: ${filePath}`);
  
  try {
    let content = fs.readFileSync(filePath, 'utf8');
    const originalContent = content;
    
    // Skip if already updated
    if (content.includes('DataContainer') || content.includes('ApiErrorAlert')) {
      console.log(`   ⏭️  Already updated`);
      return { updated: false, reason: 'already_updated' };
    }
    
    // Skip non-React components
    if (!content.includes('useSimpleFetch') && !content.includes('useState')) {
      console.log(`   ⏭️  No API calls detected`);
      return { updated: false, reason: 'no_api_calls' };
    }

    const filename = path.basename(filePath);
    const componentName = getComponentName(filename);
    const fallbackDataType = getFallbackDataType(filename, content);
    
    // 1. Add imports
    if (content.includes("import { useSimpleFetch }")) {
      content = content.replace(
        /import { useSimpleFetch } from ['"]..\/hooks\/useSimpleFetch['"];?/,
        `import { useSimpleFetch } from '../hooks/useSimpleFetch';
import ApiErrorAlert from '../components/ApiErrorAlert';
import DataContainer from '../components/DataContainer';`
      );
    }

    // 2. Find useSimpleFetch calls and enhance them
    const apiCallMatches = [...content.matchAll(/const \{ data: (\w+), loading: (\w+)(?:, error: (\w+))?(?:, refetch: (\w+))? \} = useSimpleFetch\(([^)]+)\)/g)];
    
    if (apiCallMatches.length === 0) {
      console.log(`   ⏭️  No useSimpleFetch patterns found`);
      return { updated: false, reason: 'no_fetch_patterns' };
    }

    // Track variables for wrapper
    let mainDataVar = null;
    let mainLoadingVar = null;
    let mainErrorVar = null;
    let mainRefetchVar = null;

    // 3. Update useSimpleFetch calls to include error and refetch
    apiCallMatches.forEach(match => {
      const [fullMatch, dataVar, loadingVar, errorVar, refetchVar, apiCall] = match;
      
      if (!mainDataVar) {
        mainDataVar = dataVar;
        mainLoadingVar = loadingVar;
        mainErrorVar = errorVar || `${dataVar}Error`;
        mainRefetchVar = refetchVar || `${dataVar}Refetch`;
      }
      
      const enhancedCall = `const { data: ${dataVar}, loading: ${loadingVar}, error: ${mainErrorVar}, refetch: ${mainRefetchVar} } = useSimpleFetch(${apiCall});`;
      content = content.replace(fullMatch, enhancedCall);
    });

    // 4. Find the main return statement and wrap with DataContainer
    const returnMatch = content.match(/(return \([\s\S]*?\);)(?=\s*};\s*$)/);
    if (!returnMatch) {
      console.log(`   ❌ Could not find return statement`);
      return { updated: false, reason: 'no_return_statement' };
    }

    const returnStatement = returnMatch[1];
    const returnContent = returnStatement.replace('return (', '').replace(/\);$/, '');
    
    // Create the wrapped version
    const wrappedReturn = `return (
    <DataContainer
      loading={${mainLoadingVar}}
      error={${mainErrorVar}}
      data={${mainDataVar}}
      onRetry={${mainRefetchVar}}
      fallbackDataType="${fallbackDataType}"
      context="${componentName.toLowerCase()} data"
      showTechnicalDetails={true}
      enableFallback={true}
    >
      <div>
        ${returnContent}
      </div>
    </DataContainer>
  );`;

    content = content.replace(returnStatement, wrappedReturn);

    // 5. Write updated file
    fs.writeFileSync(filePath, content);
    console.log(`   ✅ Updated successfully (${fallbackDataType} data type)`);
    
    return { 
      updated: true, 
      dataType: fallbackDataType,
      apiCalls: apiCallMatches.length 
    };
    
  } catch (error) {
    console.log(`   ❌ Error: ${error.message}`);
    return { updated: false, reason: 'error', error: error.message };
  }
}

// Process all page files
function updateAllPages() {
  console.log('🚀 Bulk Page Update - API Error Handling');
  console.log('==========================================');
  
  if (!fs.existsSync(PAGES_DIR)) {
    console.error(`❌ Pages directory not found: ${PAGES_DIR}`);
    process.exit(1);
  }

  const files = fs.readdirSync(PAGES_DIR, { recursive: true })
    .filter(file => file.endsWith('.jsx'))
    .map(file => path.join(PAGES_DIR, file));

  console.log(`📁 Found ${files.length} page files to process\n`);

  const results = {
    updated: 0,
    skipped: 0,
    errors: 0,
    reasons: {}
  };

  files.forEach((file, index) => {
    console.log(`[${index + 1}/${files.length}]`);
    const result = updatePageFile(file);
    
    if (result.updated) {
      results.updated++;
    } else {
      results.skipped++;
      if (result.reason) {
        results.reasons[result.reason] = (results.reasons[result.reason] || 0) + 1;
      }
      if (result.error) {
        results.errors++;
      }
    }
  });

  console.log('\n📊 BULK UPDATE SUMMARY');
  console.log('=======================');
  console.log(`✅ Updated: ${results.updated} files`);
  console.log(`⏭️  Skipped: ${results.skipped} files`);
  console.log(`❌ Errors: ${results.errors} files`);
  
  if (Object.keys(results.reasons).length > 0) {
    console.log('\n📋 Skip reasons:');
    Object.entries(results.reasons).forEach(([reason, count]) => {
      console.log(`   ${reason}: ${count} files`);
    });
  }

  console.log('\n🎯 NEXT STEPS:');
  console.log('1. Review updated files for any syntax issues');
  console.log('2. Test a few key pages manually');
  console.log('3. Run: npm run build (to check for errors)');
  console.log('4. Fix CloudFront routing for API endpoints');
  console.log('5. Run: node test-api-routing.js (to verify fix)');
}

// Run the update
updateAllPages();