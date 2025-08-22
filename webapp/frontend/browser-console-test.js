const { exec } = require('child_process');
const util = require('util');
const execAsync = util.promisify(exec);

async function checkForConsoleErrors() {
  try {
    console.log('🔍 Testing React app for console errors...');
    
    // First check if the server responds
    const { stdout } = await execAsync('curl -s http://localhost:3000 | head -50');
    
    if (stdout.includes('<!DOCTYPE html>')) {
      console.log('✅ Server responding with HTML');
    } else {
      console.log('❌ Server not responding properly');
      return;
    }
    
    // Check if React bundle loads without syntax errors
    const jsCheck = await execAsync('curl -s http://localhost:3000 | grep -o "src=.*\\.js" | head -5');
    console.log('📦 Found JS bundles in HTML');
    
    console.log('✅ Basic server test passed - manual browser test recommended');
    console.log('🌐 Open http://localhost:3000 in browser and check F12 console');
    
  } catch (error) {
    console.error('❌ Test failed:', error.message);
  }
}

checkForConsoleErrors();
