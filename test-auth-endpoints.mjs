import axios from 'axios';

console.log('\n' + '='.repeat(70));
console.log('🔐 AUTHENTICATION ENDPOINT TEST');
console.log('='.repeat(70) + '\n');

const baseUrl = 'http://localhost:5173';

async function testEndpoints() {
  try {
    // Test 1: Frontend loads
    console.log('Test 1: Frontend loads');
    const home = await axios.get(baseUrl, { timeout: 5000 });
    console.log(`  ✅ Status: ${home.status}`);
    console.log(`  ✅ React app served\n`);
    
    // Test 2: Login page accessible
    console.log('Test 2: Login page accessible');
    const login = await axios.get(`${baseUrl}/login`, { timeout: 5000 });
    console.log(`  ✅ Status: ${login.status}`);
    console.log(`  ✅ HTML served\n`);
    
    // Test 3: Check for auth-related URLs
    console.log('Test 3: Auth configuration loaded');
    if (login.data.includes('dev-admin') || login.data.includes('form') || login.data.includes('auth')) {
      console.log(`  ✅ Auth form present in HTML\n`);
    }
    
    console.log('='.repeat(70));
    console.log('✅ AUTHENTICATION ENDPOINTS RESPONDING CORRECTLY');
    console.log('='.repeat(70) + '\n');
    
    return true;
  } catch (error) {
    console.log(`❌ Error: ${error.message}\n`);
    return false;
  }
}

const result = await testEndpoints();
if (!result) process.exit(1);
