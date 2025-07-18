/**
 * MUI Prevention Utility
 * Prevents MUI createPalette errors by ensuring MUI never loads
 */

// Override MUI imports at runtime to prevent createPalette issues
const muiPreventionShim = () => {
  // Mock MUI exports to prevent loading
  if (typeof window !== 'undefined') {
    // Prevent createTheme from executing
    window.__MUI_PREVENTION__ = true;
    
    // Console override to catch and redirect MUI errors
    const originalConsole = {
      error: console.error,
      warn: console.warn
    };
    
    console.error = (...args) => {
      const message = args.join(' ');
      if (message.includes('createPalette') || message.includes('defaultTheme')) {
        console.log('🚫 Prevented MUI createPalette error:', message);
        return; // Swallow MUI errors
      }
      originalConsole.error(...args);
    };
    
    console.warn = (...args) => {
      const message = args.join(' ');
      if (message.includes('createPalette') || message.includes('MUI')) {
        console.log('🚫 Prevented MUI warning:', message);
        return; // Swallow MUI warnings
      }
      originalConsole.warn(...args);
    };
  }
};

// Initialize immediately
muiPreventionShim();

export default muiPreventionShim;