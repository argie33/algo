import React from 'react';
import { Alert, Box, Typography } from '@mui/material';
import { Warning } from '@mui/icons-material';

/**
 * SafeComponentWrapper - Handles undefined component exports gracefully
 * Provides a fallback when components fail to import or are undefined
 */
const SafeComponentWrapper = ({ component: Component, fallback, name, ...props }) => {
  // Check if component is valid
  if (!Component) {
    const errorMessage = `Component "${name || 'Unknown'}" is undefined. This usually means there's an import/export issue.`;
    console.error(errorMessage);
    
    // Return custom fallback or default error UI
    if (fallback) {
      return fallback;
    }
    
    return (
      <Box sx={{ p: 2, border: '1px solid #f44336', borderRadius: 1, bgcolor: '#fef2f2' }}>
        <Alert 
          severity="error" 
          icon={<Warning />}
          sx={{ mb: 1 }}
        >
          <Typography variant="subtitle2" gutterBottom>
            Component Loading Error
          </Typography>
          <Typography variant="body2">
            {errorMessage}
          </Typography>
        </Alert>
        <Typography variant="caption" color="text.secondary">
          Please check the component import/export statements.
        </Typography>
      </Box>
    );
  }
  
  // Check if component is a valid React component
  if (typeof Component !== 'function' && typeof Component !== 'object') {
    const errorMessage = `Invalid component type for "${name || 'Unknown'}". Expected function or object, got ${typeof Component}.`;
    console.error(errorMessage);
    
    return (
      <Box sx={{ p: 2, border: '1px solid #f44336', borderRadius: 1, bgcolor: '#fef2f2' }}>
        <Alert severity="error" icon={<Warning />}>
          <Typography variant="body2">
            {errorMessage}
          </Typography>
        </Alert>
      </Box>
    );
  }
  
  try {
    // Render the component safely
    return <Component {...props} />;
  } catch (error) {
    console.error(`Error rendering component "${name || 'Unknown'}":`, error);
    
    return (
      <Box sx={{ p: 2, border: '1px solid #f44336', borderRadius: 1, bgcolor: '#fef2f2' }}>
        <Alert severity="error" icon={<Warning />}>
          <Typography variant="subtitle2" gutterBottom>
            Component Render Error
          </Typography>
          <Typography variant="body2">
            {error.message || 'Unknown error occurred while rendering component'}
          </Typography>
        </Alert>
      </Box>
    );
  }
};

/**
 * Higher-order component version for wrapping components
 */
export const withSafeWrapper = (Component, componentName) => {
  return React.forwardRef((props, ref) => (
    <SafeComponentWrapper 
      component={Component} 
      name={componentName}
      ref={ref}
      {...props} 
    />
  ));
};

/**
 * Hook for safely importing components
 */
export const useSafeComponent = (importFn, componentName) => {
  const [Component, setComponent] = React.useState(null);
  const [error, setError] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  
  React.useEffect(() => {
    let mounted = true;
    
    const loadComponent = async () => {
      try {
        const module = await importFn();
        
        if (!mounted) return;
        
        // Handle both default and named exports
        const comp = module.default || module[componentName] || module;
        
        if (!comp) {
          throw new Error(`Component "${componentName}" not found in module`);
        }
        
        setComponent(() => comp);
        setError(null);
      } catch (err) {
        if (!mounted) return;
        
        setError(err);
        setComponent(null);
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    };
    
    loadComponent();
    
    return () => {
      mounted = false;
    };
  }, [importFn, componentName]);
  
  return { Component, error, loading };
};

export default SafeComponentWrapper;