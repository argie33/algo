#!/usr/bin/env node

const { app } = require('./lambda/index');

const PORT = 3001;

console.log('🧪 Testing Lambda function locally...');
console.log('📊 Environment: development');
console.log('🔗 Server will start on http://localhost:3001');

// Start the server
app.listen(PORT, () => {
  console.log(`✅ Lambda function test server running on http://localhost:${PORT}`);
  console.log('');
  console.log('📋 Test endpoints:');
  console.log(`   Health: http://localhost:${PORT}/health`);
  console.log(`   API Info: http://localhost:${PORT}/`);
  console.log(`   Stocks: http://localhost:${PORT}/stocks`);
  console.log(`   Market: http://localhost:${PORT}/market`);
  console.log('');
  console.log('💡 Press Ctrl+C to stop the server');
  console.log('');
});

// Handle graceful shutdown
process.on('SIGINT', () => {
  console.log('\n🛑 Shutting down test server...');
  process.exit(0);
}); 