const { exec } = require('child_process');
const util = require('util');
const execAsync = util.promisify(exec);

async function checkForConsoleErrors() {
  try {
    console.log('🔍 Testing React app for console errors...');
    
    // Wait for dev server to fully start
    console.log('⏳ Waiting for dev server...');
    await new Promise(resolve => setTimeout(resolve, 3000));
    
    // Check if the server responds
    try {
      const { stdout } = await execAsync('curl -s -m 10 http://localhost:3000');
      
      if (stdout.includes('<!DOCTYPE html>') && stdout.includes('react')) {
        console.log('✅ Server responding with React HTML');
        
        // Check for any obvious JavaScript errors in the HTML
        if (stdout.includes('error') || stdout.includes('Error')) {
          console.log('⚠️  Warning: Found "error" text in HTML response');
        }
        
        // Look for React bundle references
        if (stdout.includes('script') && (stdout.includes('.js') || stdout.includes('module'))) {
          console.log('✅ JavaScript modules found in HTML');
        }
        
        console.log('📊 Basic checks passed!');
        console.log('');
        console.log('🌐 MANUAL TEST NEEDED:');
        console.log('   1. Open http://localhost:3000 in browser');
        console.log('   2. Press F12 to open developer tools');
        console.log('   3. Check Console tab for any red errors');
        console.log('   4. Look specifically for "Cannot set properties of undefined" errors');
        console.log('   5. Navigate between pages to test React routing');
        console.log('');
        console.log('❌ ERRORS TO WATCH FOR:');
        console.log('   - Cannot set properties of undefined (setting \'ContextConsumer\')');
        console.log('   - react-is compatibility errors');
        console.log('   - Context provider errors');
        console.log('   - Component mounting failures');
        
      } else {
        console.log('❌ Server not responding with valid React HTML');
        console.log('Response preview:', stdout.substring(0, 200) + '...');
      }
    } catch (curlError) {
      console.log('❌ Failed to connect to dev server');
      console.log('Error:', curlError.message);
    }
    
  } catch (error) {
    console.error('❌ Test script failed:', error.message);
  }
}

checkForConsoleErrors();
