/**
 * React Fix Verification
 * Tests that React is properly available to prevent useLayoutEffect errors
 */

export const verifyReactAvailability = () => {
  const checks = {
    windowReact: typeof window !== 'undefined' && window.React,
    windowF: typeof window !== 'undefined' && window.F,
    globalReact: typeof globalThis !== 'undefined' && globalThis.React,
    globalF: typeof globalThis !== 'undefined' && globalThis.F,
    useLayoutEffect: false,
    useMemo: false,
    reactVersion: null
  };

  // Check if React hooks are available
  try {
    if (window.React) {
      checks.useLayoutEffect = typeof window.React.useLayoutEffect === 'function';
      checks.useMemo = typeof window.React.useMemo === 'function';
      checks.reactVersion = window.React.version;
    }
  } catch (error) {
    console.warn('Error checking React availability:', error);
  }

  const allGood = checks.windowReact && checks.windowF && checks.useLayoutEffect && checks.useMemo;

  if (allGood) {
    console.log('✅ React availability check passed:', checks);
  } else {
    console.error('❌ React availability check failed:', checks);
  }

  return { checks, allGood };
};

// Auto-run verification in development
if (process.env.NODE_ENV === 'development') {
  setTimeout(() => {
    verifyReactAvailability();
  }, 100);
}

export default verifyReactAvailability;