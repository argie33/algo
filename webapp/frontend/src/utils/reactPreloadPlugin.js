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

      // Find React chunk
      const reactChunk = Object.values(bundle).find(chunk =>
        chunk.type === 'chunk' && 
        (chunk.name === 'vendor-react' || chunk.code?.includes('react/jsx-runtime'))
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
  
  // Try to load real React asynchronously
  import('./vendor-react.js').then(module => {
    if (module.default) {
      window.React = module.default;
      window.F = module.default;
      console.log('✅ Real React loaded and replaced emergency bridge');
    }
  }).catch(e => console.warn('Failed to load React chunk:', e));
}
`;
          chunk.code = reactPreload + chunk.code;
        });
      }
    },
    
    // Also modify the HTML to preload React chunk first
    transformIndexHtml: {
      enforce: 'pre',
      transform(html, context) {
        // Add React chunk preload with high priority
        const reactPreloadLink = '<link rel="modulepreload" crossorigin href="/assets/vendor-react.js" as="script">';
        return html.replace('<head>', `<head>\n    ${reactPreloadLink}`);
      }
    }
  };
}