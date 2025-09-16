#!/usr/bin/env node

const { execSync } = require('child_process');
const fs = require('fs');

// Test local frontend for React Context errors
console.log('🧪 Testing Local Frontend for React Context Issues...\n');

// Check if dev server is running
try {
  const response = execSync('curl -s http://localhost:3000', { encoding: 'utf8' });

  if (response.includes('Fix React Context ContextConsumer error')) {
    console.log('✅ React Context fix detected in HTML');
  } else {
    console.log('❌ React Context fix NOT found in HTML');
  }

  if (response.includes('<div id="root">')) {
    console.log('✅ Root element found');
  } else {
    console.log('❌ Root element missing');
  }

  if (response.includes('main.jsx')) {
    console.log('✅ React app script tag found');
  } else {
    console.log('❌ React app script tag missing');
  }

} catch (error) {
  console.log('❌ Local dev server not responding');
  console.log('Error:', error.message);
}

// Check for common React Context error patterns in built files
console.log('\n🔍 Checking built files for React Context issues...');

const distPath = '/home/stocks/algo/webapp/frontend/dist';
if (fs.existsSync(distPath)) {
  try {
    const files = fs.readdirSync(`${distPath}/assets`).filter(f => f.includes('index-'));
    if (files.length > 0) {
      const mainFile = `${distPath}/assets/${files[0]}`;
      const content = fs.readFileSync(mainFile, 'utf8');

      if (content.includes('ContextConsumer')) {
        console.log('⚠️  ContextConsumer references found in built bundle');
      } else {
        console.log('✅ No ContextConsumer references in built bundle');
      }

      if (content.includes('hoist-non-react-statics')) {
        console.log('⚠️  hoist-non-react-statics found in bundle (potential issue)');
      } else {
        console.log('✅ No hoist-non-react-statics in bundle');
      }
    }
  } catch (error) {
    console.log('❌ Error checking built files:', error.message);
  }
} else {
  console.log('❌ Dist folder not found');
}

console.log('\n📋 Test Complete');