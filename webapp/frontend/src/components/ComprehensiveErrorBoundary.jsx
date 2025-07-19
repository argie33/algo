/**
 * Comprehensive Error Boundary Component
 * Catches all React errors and provides detailed error reporting with recovery options
 */

import React from 'react';
import comprehensiveErrorService from '../services/comprehensiveErrorService';

class ComprehensiveErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            hasError: false,
            error: null,
            errorInfo: null,
            errorId: null,
            showDetails: false,
            retryCount: 0
        };
    }

    static getDerivedStateFromError(error) {
        // Update state so the next render will show the fallback UI
        return { hasError: true };
    }

    componentDidCatch(error, errorInfo) {
        // Handle the error comprehensively
        const errorResponse = comprehensiveErrorService.handleError(error, {
            type: 'COMPONENT_ERROR',
            componentStack: errorInfo.componentStack,
            errorBoundary: this.props.name || 'Unknown',
            props: this.props.children?.props,
            retryCount: this.state.retryCount
        });

        this.setState({
            error,
            errorInfo,
            errorId: errorResponse.errorId,
            userMessage: errorResponse.userMessage,
            canRetry: errorResponse.canRetry,
            suggestedActions: errorResponse.suggestedActions
        });

        // Report to parent component if callback provided
        if (this.props.onError) {
            this.props.onError(error, errorInfo, errorResponse);
        }
    }

    handleRetry = () => {
        this.setState(prevState => ({
            hasError: false,
            error: null,
            errorInfo: null,
            errorId: null,
            showDetails: false,
            retryCount: prevState.retryCount + 1
        }));
    };

    handleRefresh = () => {
        window.location.reload();
    };

    handleReportBug = () => {
        const errorReport = {
            errorId: this.state.errorId,
            error: this.state.error?.message,
            stack: this.state.error?.stack,
            componentStack: this.state.errorInfo?.componentStack,
            url: window.location.href,
            timestamp: new Date().toISOString(),
            userAgent: navigator.userAgent
        };

        // Copy to clipboard
        navigator.clipboard.writeText(JSON.stringify(errorReport, null, 2))
            .then(() => {
                alert('Error report copied to clipboard. Please send this to support.');
            })
            .catch(() => {
                console.log('Error report:', errorReport);
                alert('Error report logged to console. Please copy and send to support.');
            });
    };

    toggleDetails = () => {
        this.setState(prevState => ({
            showDetails: !prevState.showDetails
        }));
    };

    render() {
        if (this.state.hasError) {
            const { error, errorInfo, errorId, showDetails, retryCount } = this.state;
            const { fallback: FallbackComponent, showRetry = true, maxRetries = 3 } = this.props;

            // If custom fallback provided, use it
            if (FallbackComponent) {
                return (
                    <FallbackComponent 
                        error={error}
                        errorInfo={errorInfo}
                        errorId={errorId}
                        onRetry={this.handleRetry}
                        onRefresh={this.handleRefresh}
                        onReportBug={this.handleReportBug}
                        canRetry={retryCount < maxRetries}
                    />
                );
            }

            // Default error UI
            return (
                <div style={{
                    padding: '20px',
                    margin: '20px',
                    border: '2px solid #f44336',
                    borderRadius: '8px',
                    backgroundColor: '#fff3f3',
                    fontFamily: 'Arial, sans-serif'
                }}>
                    <div style={{ display: 'flex', alignItems: 'center', marginBottom: '16px' }}>
                        <span style={{ fontSize: '24px', marginRight: '8px' }}>🚨</span>
                        <h2 style={{ margin: 0, color: '#f44336' }}>Something went wrong</h2>
                    </div>

                    <p style={{ marginBottom: '16px', color: '#666' }}>
                        {this.state.userMessage || 'An unexpected error occurred in this component.'}
                    </p>

                    {errorId && (
                        <div style={{ 
                            padding: '8px 12px', 
                            backgroundColor: '#f5f5f5', 
                            borderRadius: '4px',
                            marginBottom: '16px',
                            fontSize: '12px',
                            fontFamily: 'monospace'
                        }}>
                            Error ID: {errorId}
                        </div>
                    )}

                    <div style={{ 
                        display: 'flex', 
                        gap: '12px', 
                        flexWrap: 'wrap',
                        marginBottom: '16px'
                    }}>
                        {showRetry && retryCount < maxRetries && (
                            <button
                                onClick={this.handleRetry}
                                style={{
                                    padding: '8px 16px',
                                    backgroundColor: '#4caf50',
                                    color: 'white',
                                    border: 'none',
                                    borderRadius: '4px',
                                    cursor: 'pointer'
                                }}
                            >
                                Try Again ({maxRetries - retryCount} attempts left)
                            </button>
                        )}

                        <button
                            onClick={this.handleRefresh}
                            style={{
                                padding: '8px 16px',
                                backgroundColor: '#2196f3',
                                color: 'white',
                                border: 'none',
                                borderRadius: '4px',
                                cursor: 'pointer'
                            }}
                        >
                            Refresh Page
                        </button>

                        <button
                            onClick={this.handleReportBug}
                            style={{
                                padding: '8px 16px',
                                backgroundColor: '#ff9800',
                                color: 'white',
                                border: 'none',
                                borderRadius: '4px',
                                cursor: 'pointer'
                            }}
                        >
                            Report Issue
                        </button>

                        <button
                            onClick={this.toggleDetails}
                            style={{
                                padding: '8px 16px',
                                backgroundColor: '#666',
                                color: 'white',
                                border: 'none',
                                borderRadius: '4px',
                                cursor: 'pointer'
                            }}
                        >
                            {showDetails ? 'Hide Details' : 'Show Details'}
                        </button>
                    </div>

                    {showDetails && (
                        <div style={{
                            backgroundColor: '#f8f8f8',
                            padding: '16px',
                            borderRadius: '4px',
                            overflow: 'auto',
                            maxHeight: '300px'
                        }}>
                            <h4 style={{ margin: '0 0 12px 0' }}>Error Details:</h4>
                            
                            <div style={{ marginBottom: '12px' }}>
                                <strong>Error Message:</strong>
                                <pre style={{ 
                                    margin: '4px 0', 
                                    padding: '8px', 
                                    backgroundColor: '#fff',
                                    border: '1px solid #ddd',
                                    borderRadius: '4px',
                                    fontSize: '12px',
                                    whiteSpace: 'pre-wrap'
                                }}>
                                    {error?.message || 'Unknown error'}
                                </pre>
                            </div>

                            {error?.stack && (
                                <div style={{ marginBottom: '12px' }}>
                                    <strong>Stack Trace:</strong>
                                    <pre style={{ 
                                        margin: '4px 0', 
                                        padding: '8px', 
                                        backgroundColor: '#fff',
                                        border: '1px solid #ddd',
                                        borderRadius: '4px',
                                        fontSize: '11px',
                                        whiteSpace: 'pre-wrap'
                                    }}>
                                        {error.stack}
                                    </pre>
                                </div>
                            )}

                            {errorInfo?.componentStack && (
                                <div>
                                    <strong>Component Stack:</strong>
                                    <pre style={{ 
                                        margin: '4px 0', 
                                        padding: '8px', 
                                        backgroundColor: '#fff',
                                        border: '1px solid #ddd',
                                        borderRadius: '4px',
                                        fontSize: '11px',
                                        whiteSpace: 'pre-wrap'
                                    }}>
                                        {errorInfo.componentStack}
                                    </pre>
                                </div>
                            )}

                            <div style={{ marginTop: '12px', fontSize: '12px', color: '#666' }}>
                                Retry count: {retryCount}
                            </div>
                        </div>
                    )}

                    {retryCount >= maxRetries && (
                        <div style={{
                            marginTop: '16px',
                            padding: '12px',
                            backgroundColor: '#fff3cd',
                            border: '1px solid #ffeaa7',
                            borderRadius: '4px',
                            color: '#856404'
                        }}>
                            ⚠️ Maximum retry attempts reached. Please refresh the page or contact support.
                        </div>
                    )}
                </div>
            );
        }

        return this.props.children;
    }
}

export default ComprehensiveErrorBoundary;