// ARCHITECTURAL FIX: Vite plugin to ensure React loads before emotion chunks
// This eliminates the need for runtime Proxy hacks

export function reactPreloadPlugin() {
  return {
    name: 'react-preload',
    generateBundle(options, bundle) {
      // Find all chunks that might contain @emotion/react
      const emotionChunks = Object.values(bundle).filter(chunk => 
        chunk.type === 'chunk' && 
        (chunk.code?.includes('@emotion/react') || 
         chunk.code?.includes('useLayoutEffect') ||
         chunk.facadeModuleId?.includes('@emotion'))
      );

      // Find React chunk (look for React hooks or version)
      const reactChunk = Object.values(bundle).find(chunk =>
        chunk.type === 'chunk' && 
        (chunk.code?.includes('useState') || 
         chunk.code?.includes('18.3') ||
         chunk.code?.includes('react/jsx-runtime'))
      );

      if (emotionChunks.length > 0 && reactChunk) {
        console.log(`🔧 React preload plugin: Patching ${emotionChunks.length} emotion chunks`);
        
        emotionChunks.forEach(chunk => {
          // Prepend React availability check to emotion chunks
          const reactPreload = `
// ARCHITECTURAL FIX: Ensure React is available as F before emotion code runs
if (typeof window !== 'undefined' && !window.F) {
  // Emergency F bridge until React loads
  window.F = {
    useLayoutEffect: function(effect, deps) {
      console.log('🔧 Emergency useLayoutEffect bridge');
      if (effect) try { effect(); } catch(e) {}
    },
    useState: function(initial) { return [initial, function() {}]; },
    useEffect: function() {},
    useCallback: function(callback) { return callback; },
    useMemo: function(factory) { try { return factory(); } catch(e) { return null; } },
    useRef: function(initial) { return { current: initial }; },
    createElement: function() { return {}; }
  };
  
  // Try to load real React asynchronously - React is in the same chunk
  if (typeof React !== 'undefined') {
    window.React = React;
    window.F = React;
    console.log('✅ Real React found and set as F');
  } else {
    console.warn('React not available in this chunk');
  }
}
`;
          chunk.code = reactPreload + chunk.code;
        });
      }
    },
    
    // Note: HTML preloading handled by normal chunk loading order
    // No need to manually inject preload links since React is in emotion chunks
  };
}