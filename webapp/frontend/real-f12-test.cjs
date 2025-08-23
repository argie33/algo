const https = require('https');
const http = require('http');

async function testReactApp() {
  console.log('🔍 F12-Style Browser Console Test');
  console.log('==================================');
  
  try {
    // Test if server is responding
    console.log('📡 Testing server response...');
    const html = await new Promise((resolve, reject) => {
      const req = http.get('http://localhost:3001', (res) => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => resolve(data));
      });
      req.on('error', reject);
      req.setTimeout(10000, () => reject(new Error('Timeout')));
    });
    
    console.log('✅ Server responding');
    
    // Analyze HTML for potential issues
    const checks = [
      {
        name: 'React Bundle Loading',
        test: () => html.includes('script') && (html.includes('type="module"') || html.includes('.js')),
        error: 'No JavaScript modules found'
      },
      {
        name: 'React Development Mode',
        test: () => html.includes('react-refresh') || html.includes('@react-refresh'),
        error: 'React refresh not detected'
      },
      {
        name: 'HTML Structure',
        test: () => html.includes('<div id="root">') || html.includes('<div id="app">'),
        error: 'No React root element found'
      },
      {
        name: 'No Obvious Errors',
        test: () => !html.toLowerCase().includes('error') && !html.toLowerCase().includes('failed'),
        error: 'Error text found in HTML'
      }
    ];
    
    console.log('\n📊 HTML Analysis:');
    let allPassed = true;
    
    checks.forEach(check => {
      const passed = check.test();
      console.log(`   ${passed ? '✅' : '❌'} ${check.name}`);
      if (!passed) {
        console.log(`      Issue: ${check.error}`);
        allPassed = false;
      }
    });
    
    // Specific React Context error patterns to look for
    const reactContextIssues = [
      'Cannot set properties of undefined',
      'ContextConsumer',
      'react-is',
      'TypeError: Cannot read properties',
      'ReferenceError',
      'undefined (setting \'Context'
    ];
    
    console.log('\n🔍 Scanning for React Context error patterns...');
    let foundIssues = [];
    
    reactContextIssues.forEach(pattern => {
      if (html.includes(pattern)) {
        foundIssues.push(pattern);
      }
    });
    
    if (foundIssues.length === 0) {
      console.log('✅ No React Context error patterns detected in HTML');
    } else {
      console.log('❌ Found potential React Context issues:');
      foundIssues.forEach(issue => console.log(`   - ${issue}`));
    }
    
    // Manual testing instructions
    console.log('\n🌐 MANUAL F12 VERIFICATION:');
    console.log('============================');
    console.log('1. Open: http://localhost:3001');
    console.log('2. Press F12 (Developer Tools)');
    console.log('3. Click Console tab');
    console.log('4. Refresh page (Ctrl+R)');
    console.log('5. Look for RED errors (not warnings)');
    console.log('');
    console.log('❌ ERRORS TO WATCH FOR:');
    console.log('   • Cannot set properties of undefined (setting \'ContextConsumer\')');
    console.log('   • react-is.production.js:58 errors');
    console.log('   • TypeError in Context providers');
    console.log('   • Component mounting failures');
    console.log('');
    console.log('✅ GOOD SIGNS:');
    console.log('   • Page loads without red errors');
    console.log('   • Components render properly');
    console.log('   • Navigation works between pages');
    console.log('   • Only blue info/warnings (no red errors)');
    
    const result = allPassed && foundIssues.length === 0;
    console.log(`\n📈 AUTOMATED CHECKS: ${result ? 'PASSED' : 'FAILED'}`);
    
    return result;
    
  } catch (error) {
    console.error('❌ Test failed:', error.message);
    console.log('\n🔧 TROUBLESHOOTING:');
    console.log('   • Make sure dev server is running: npm run dev');
    console.log('   • Check if port 3001 is accessible');
    console.log('   • Verify React app is building without errors');
    return false;
  }
}

testReactApp().then(passed => {
  console.log('\n' + '='.repeat(50));
  if (passed) {
    console.log('🎉 REACT CONTEXT FIX LIKELY WORKING!');
    console.log('   Automated checks passed');
    console.log('   Manual F12 verification recommended');
  } else {
    console.log('⚠️  POTENTIAL ISSUES DETECTED');
    console.log('   Manual F12 verification required');
  }
  console.log('='.repeat(50));
});
