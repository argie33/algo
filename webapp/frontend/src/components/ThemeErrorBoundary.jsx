import React from 'react';

class ThemeErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    console.error('🚨 Theme Error Boundary caught error:', error);
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    console.error('🚨 Theme Error Boundary - Full error details:', {
      error: error,
      errorInfo: errorInfo,
      stack: error.stack,
      name: error.name,
      message: error.message
    });
    
    this.setState({
      error: error,
      errorInfo: errorInfo
    });
  }

  render() {
    if (this.state.hasError) {
      console.log('🔧 Theme Error Boundary - Rendering fallback UI');
      
      // Don't use any MUI components - just plain HTML
      return (
        <div style={{
          padding: '20px',
          textAlign: 'center',
          fontFamily: 'Arial, sans-serif',
          maxWidth: '600px',
          margin: '50px auto',
          border: '1px solid #ccc',
          borderRadius: '8px',
          backgroundColor: '#f9f9f9'
        }}>
          <h1 style={{ color: '#d32f2f' }}>Theme Loading Error</h1>
          <p><strong>Error:</strong> {this.state.error?.message || 'Unknown theme error'}</p>
          <p style={{ fontSize: '14px', color: '#666' }}>
            The application theme failed to load. The page will reload automatically.
          </p>
          
          <details style={{ marginTop: '20px', textAlign: 'left' }}>
            <summary style={{ cursor: 'pointer', fontWeight: 'bold' }}>
              Technical Details
            </summary>
            <pre style={{ 
              backgroundColor: '#f0f0f0', 
              padding: '10px', 
              borderRadius: '4px',
              fontSize: '12px',
              overflow: 'auto',
              maxHeight: '200px'
            }}>
              {this.state.error?.stack || 'No stack trace available'}
            </pre>
          </details>
          
          <button 
            onClick={() => window.location.reload()}
            style={{
              marginTop: '20px',
              padding: '10px 20px',
              backgroundColor: '#1976d2',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer'
            }}
          >
            Reload Application
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ThemeErrorBoundary;