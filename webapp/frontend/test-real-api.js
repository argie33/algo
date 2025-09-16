/**
 * Real API Test - Verify actual backend connectivity
 * This test demonstrates the difference between mocked and real API calls
 */

console.log('🔍 Testing Real vs Mocked API Behavior');

// Test 1: Try to import real API service
console.log('\n📡 Testing Real API Service Import:');
try {
  // Import without mocking
  const apiService = await import('./src/services/api.js');
  console.log('✅ Real API service imported successfully');
  console.log('🔧 API service methods:', Object.keys(apiService.default || apiService));
  
  // Test a simple endpoint that should exist
  if (apiService.default && apiService.default.get) {
    console.log('🌐 Testing real API call to /health endpoint...');
    try {
      const response = await apiService.default.get('/health', { timeout: 5000 });
      console.log('✅ Real API responded:', response?.status || 'Success');
      console.log('📊 Real data structure:', typeof response?.data);
    } catch (error) {
      console.log('⚠️ Real API call failed:', error.message);
      console.log('💡 This is expected if backend is not running');
    }
  } else {
    console.log('❌ API service does not have expected get method');
  }
} catch (error) {
  console.log('❌ Failed to import real API service:', error.message);
}

// Test 2: Check if we can make real fetch calls
console.log('\n🌐 Testing Real Fetch to Backend:');
try {
  const response = await fetch('http://localhost:8081/health', { 
    method: 'GET',
    timeout: 5000 
  });
  console.log('✅ Real fetch succeeded:', response.status);
  const data = await response.text();
  console.log('📊 Real response data:', data.substring(0, 100) + '...');
} catch (error) {
  console.log('⚠️ Real fetch failed:', error.message);
  console.log('💡 Backend may not be running on localhost:8081');
}

// Test 3: Show what mocked API would look like
console.log('\n🎭 Comparing with Mock Behavior:');
console.log('✅ Mocked API: Always returns predefined success responses');
console.log('✅ Mocked API: No network calls, no timeouts, no real errors');
console.log('✅ Mocked API: Tests pass regardless of backend state');
console.log('⚠️ Real API: Depends on backend availability and real data');
console.log('⚠️ Real API: Can fail due to network, server, or data issues');
console.log('✅ Real API: Tests validate actual system integration');

console.log('\n📋 Summary:');
console.log('• Our passing tests use BOTH approaches:');
console.log('  - UI Components: Use mocked APIs (fast, isolated, stable)');
console.log('  - Auth Service: Uses real devAuth service (functional validation)');
console.log('  - Integration: Mix of real services + mocked external APIs');
console.log('• This hybrid approach ensures:');
console.log('  - Fast test execution (mocked dependencies)');
console.log('  - Real functionality validation (unmocked core services)');
console.log('  - Stable test environment (predictable responses)');
