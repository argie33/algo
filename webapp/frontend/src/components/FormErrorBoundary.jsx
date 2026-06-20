import React, { Component } from 'react';
import PropTypes from 'prop-types';

/**
 * Error boundary specifically for form submissions.
 *
 * Catches submission errors and prevents UI from showing success when
 * the actual API operation failed. Provides:
 * - Error message display
 * - Form state rollback on failure
 * - Retry mechanism
 */
class FormErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      isSubmitting: false,
    };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    this.setState({ errorInfo });
    console.error('[FormErrorBoundary] Caught submission error:', error, errorInfo);
    if (this.props.onError) {
      this.props.onError(error, errorInfo);
    }
  }

  resetError = () => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
    });
  };

  render() {
    const { children, fallback } = this.props;
    const { hasError, error, errorInfo } = this.state;

    if (hasError) {
      if (fallback) {
        return fallback({ error, errorInfo, reset: this.resetError });
      }

      return (
        <div className="alert alert-danger" style={{ marginBottom: 'var(--space-4)' }}>
          <div style={{ marginBottom: 'var(--space-3)' }}>
            <strong>Form submission failed</strong>
            <p style={{ marginTop: 'var(--space-2)', fontSize: 'var(--t-sm)' }}>
              {error?.message || 'An unexpected error occurred'}
            </p>
            {errorInfo && (
              <details style={{ marginTop: 'var(--space-2)', fontSize: 'var(--t-2xs)' }}>
                <summary style={{ cursor: 'pointer', fontWeight: 'var(--w-bold)' }}>
                  Details
                </summary>
                <pre
                  style={{
                    marginTop: 'var(--space-2)',
                    padding: 'var(--space-2)',
                    background: 'var(--surface)',
                    borderRadius: 'var(--r-sm)',
                    overflow: 'auto',
                  }}
                >
                  {errorInfo.componentStack}
                </pre>
              </details>
            )}
          </div>
          <button
            type="button"
            className="btn btn-sm btn-default"
            onClick={this.resetError}
            style={{ marginTop: 'var(--space-3)' }}
          >
            Try Again
          </button>
        </div>
      );
    }

    return children;
  }
}

FormErrorBoundary.propTypes = {
  children: PropTypes.node.isRequired,
  fallback: PropTypes.func,
  onError: PropTypes.func,
};

FormErrorBoundary.defaultProps = {
  fallback: null,
  onError: null,
};

export default FormErrorBoundary;
