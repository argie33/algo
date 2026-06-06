import axios from 'axios';
import jsdom from 'jsdom';

const { JSDOM } = jsdom;

console.log('Fetching page from http://localhost:5177...');

try {
  const response = await axios.get('http://localhost:5177');
  const html = response.data;
  
  // Check for common error patterns in HTML
  const errorPatterns = [
    'r.slice is not a function',
    'Cannot read property .slice',
    'SyntaxError',
    'r is not defined',
  ];

  console.log('\n=== Checking for error patterns in HTML ===');
  errorPatterns.forEach(pattern => {
    if (html.includes(pattern)) {
      console.log(`⚠️  Found: ${pattern}`);
    }
  });

  // Create a virtual DOM and parse the HTML
  const dom = new JSDOM(html, {
    url: 'http://localhost:5177',
    pretendToBeVisual: true,
    resources: 'usable',
    runScripts: 'outside-only',
  });

  const { window } = dom;
  
  // Capture console messages
  const consoleLogs = [];
  const originalLog = window.console.log;
  const originalError = window.console.error;
  const originalWarn = window.console.warn;

  window.console.log = (...args) => {
    consoleLogs.push({ type: 'log', message: args.join(' ') });
    originalLog.apply(window.console, args);
  };

  window.console.error = (...args) => {
    consoleLogs.push({ type: 'error', message: args.join(' ') });
    originalError.apply(window.console, args);
  };

  window.console.warn = (...args) => {
    consoleLogs.push({ type: 'warn', message: args.join(' ') });
    originalWarn.apply(window.console, args);
  };

  // Check for runtime errors
  window.addEventListener('error', (event) => {
    console.log(`Runtime Error: ${event.message} at ${event.filename}:${event.lineno}`);
  });

  // Wait a bit for async code to run
  await new Promise(resolve => setTimeout(resolve, 2000));

  console.log('\n=== Console Logs ===');
  consoleLogs.forEach(log => {
    console.log(`[${log.type.toUpperCase()}] ${log.message}`);
  });

  console.log('\n✓ Page loaded successfully');
  
} catch (error) {
  console.error('Error fetching page:', error.message);
  if (error.response) {
    console.error('Status:', error.response.status);
    console.error('Response preview:', error.response.data?.substring(0, 200));
  }
}
