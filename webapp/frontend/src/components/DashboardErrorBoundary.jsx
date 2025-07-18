import React from 'react';

class DashboardErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { 
      hasError: false, 
      error: null, 
      errorInfo: null,
      retryCount: 0 
    };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    console.error('Dashboard Error Boundary caught an error:', error, errorInfo);
    this.setState({
      error,
      errorInfo,
      hasError: true
    });

    // Report error to monitoring service
    if (window.gtag) {
      window.gtag('event', 'exception', {
        description: error.toString(),
        fatal: false
      });
    }
  }

  handleRetry = () => {
    this.setState({ 
      hasError: false, 
      error: null, 
      errorInfo: null,
      retryCount: this.state.retryCount + 1 
    });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div  sx={{ p: 4, maxWidth: 800, mx: 'auto' }}>
          <div className="bg-white shadow-md rounded-lg" sx={{ border: '1px solid', borderColor: 'error.main' }}>
            <div className="bg-white shadow-md rounded-lg"Content sx={{ p: 4 }}>
              <div className="flex flex-col space-y-2" spacing={3} alignItems="center" textAlign="center">
                <Error sx={{ fontSize: 60, color: 'error.main' }} />
                
                <div  variant="h4" color="error.main" gutterBottom>
                  Dashboard Error
                </div>
                
                <div  variant="body1" color="text.secondary">
                  Something went wrong while loading your dashboard. This is likely due to:
                </div>

                <div className="flex flex-col space-y-2" spacing={1} sx={{ width: '100%', maxWidth: 500 }}>
                  <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="warning" variant="outlined">
                    <strong>Database Connection Issues:</strong> The backend may be unable to connect to the database
                  </div>
                  <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="warning" variant="outlined">
                    <strong>Authentication Problems:</strong> Cognito configuration may be using fallback values
                  </div>
                  <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="warning" variant="outlined">
                    <strong>API Failures:</strong> One or more API endpoints may be returning errors
                  </div>
                </div>

                <div  variant="body2" color="text.secondary" sx={{ fontFamily: 'monospace', mt: 2 }}>
                  <strong>Error:</strong> {this.state.error && this.state.error.toString()}
                </div>

                <div className="flex flex-col space-y-2" direction="row" spacing={2}>
                  <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    variant="contained"
                    onClick={this.handleRetry}
                    startIcon={<Refresh />}
                    disabled={this.state.retryCount >= 3}
                  >
                    {this.state.retryCount >= 3 ? 'Max Retries Reached' : 'Retry Dashboard'}
                  </button>
                  <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    variant="outlined"
                    onClick={() => window.location.href = '/'}
                    startIcon={<Home />}
                  >
                    Go Home
                  </button>
                  <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    variant="outlined"
                    onClick={() => {
                      const issue = encodeURIComponent(`Dashboard Error: ${this.state.error}`);
                      window.open(`https://github.com/anthropics/claude-code/issues/new?title=Dashboard%20Error&body=${issue}`);
                    }}
                    startIcon={<BugReport />}
                  >
                    Report Bug
                  </button>
                </div>

                <div  variant="caption" color="text.secondary" sx={{ mt: 2 }}>
                  Retry count: {this.state.retryCount}/3
                </div>
              </div>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default DashboardErrorBoundary;