/**
 * Simple Error Boundary - Bulletproof error handling with minimal dependencies
 * Uses only basic HTML/CSS to avoid component dependency failures
 */

import React from 'react';

class SimpleErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorId: null
    };
  }

  static getDerivedStateFromError(error) {
    return { 
      hasError: true,
      errorId: Math.random().toString(36).substr(2, 9)
    };
  }

  componentDidCatch(error, errorInfo) {
    this.setState({ error });
    
    // Simple error logging
    try {
      console.error('Application Error:', {
        id: this.state.errorId,
        message: error.message,
        stack: error.stack,
        componentStack: errorInfo.componentStack,
        timestamp: new Date().toISOString(),
        url: window.location.href
      });
    } catch (e) {
      // Even logging failed, but we don't want to crash further
    }
  }

  handleReload = () => {
    window.location.reload();
  };

  handleHome = () => {
    window.location.href = '/';
  };

  render() {
    if (this.state.hasError) {
      const { error, errorId } = this.state;
      
      return (
        <div style={{
          fontFamily: 'Arial, sans-serif',
          padding: '40px 20px',
          textAlign: 'center',
          backgroundColor: '#f9fafb',
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          alignItems: 'center'
        }}>
          <div style={{
            backgroundColor: '#ffffff',
            padding: '40px',
            borderRadius: '8px',
            boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)',
            maxWidth: '600px',
            width: '100%'
          }}>
            <div style={{
              width: '60px',
              height: '60px',
              backgroundColor: '#fee2e2',
              borderRadius: '50%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 20px'
            }}>
              <span style={{
                fontSize: '24px',
                color: '#dc2626'
              }}>⚠️</span>
            </div>

            <h1 style={{
              fontSize: '24px',
              fontWeight: 'bold',
              color: '#111827',
              marginBottom: '16px'
            }}>
              Something went wrong
            </h1>

            <p style={{
              fontSize: '16px',
              color: '#6b7280',
              marginBottom: '24px',
              lineHeight: '1.5'
            }}>
              The application encountered an unexpected error. Please try reloading the page or return to the home page.
            </p>

            {error && (
              <div style={{
                backgroundColor: '#f3f4f6',
                padding: '16px',
                borderRadius: '6px',
                marginBottom: '24px',
                textAlign: 'left'
              }}>
                <p style={{
                  fontSize: '14px',
                  color: '#374151',
                  fontFamily: 'monospace',
                  margin: '0',
                  wordBreak: 'break-word'
                }}>
                  <strong>Error:</strong> {error.message}
                </p>
                {errorId && (
                  <p style={{
                    fontSize: '12px',
                    color: '#6b7280',
                    margin: '8px 0 0',
                    fontFamily: 'monospace'
                  }}>
                    Error ID: {errorId}
                  </p>
                )}
              </div>
            )}

            <div style={{
              display: 'flex',
              gap: '12px',
              justifyContent: 'center',
              flexWrap: 'wrap'
            }}>
              <button
                onClick={this.handleReload}
                style={{
                  backgroundColor: '#3b82f6',
                  color: 'white',
                  padding: '12px 24px',
                  border: 'none',
                  borderRadius: '6px',
                  fontSize: '14px',
                  fontWeight: '500',
                  cursor: 'pointer',
                  transition: 'background-color 0.2s'
                }}
                onMouseOver={(e) => e.target.style.backgroundColor = '#2563eb'}
                onMouseOut={(e) => e.target.style.backgroundColor = '#3b82f6'}
              >
                Reload Page
              </button>

              <button
                onClick={this.handleHome}
                style={{
                  backgroundColor: '#ffffff',
                  color: '#374151',
                  padding: '12px 24px',
                  border: '1px solid #d1d5db',
                  borderRadius: '6px',
                  fontSize: '14px',
                  fontWeight: '500',
                  cursor: 'pointer',
                  transition: 'background-color 0.2s'
                }}
                onMouseOver={(e) => e.target.style.backgroundColor = '#f9fafb'}
                onMouseOut={(e) => e.target.style.backgroundColor = '#ffffff'}
              >
                Go Home
              </button>
            </div>

            <p style={{
              fontSize: '12px',
              color: '#9ca3af',
              marginTop: '24px',
              margin: '24px 0 0'
            }}>
              If this problem persists, please contact support or check the browser console for more details.
            </p>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default SimpleErrorBoundary;