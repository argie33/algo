import React from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

class DataSectionErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    };
  }

  static getDerivedStateFromError(_error) {
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    console.error(`[DataSectionError] ${this.props.section || "Data Section"}:`, error);
    console.error("Component stack:", errorInfo?.componentStack);
    this.setState({
      error,
      errorInfo,
    });
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
    if (this.props.onRetry) {
      this.props.onRetry();
    }
  };

  render() {
    if (this.state.hasError) {
      const section = this.props.section || "Data";
      const isDev = process.env.NODE_ENV === "development";

      return (
        <div style={{
          padding: "12px",
          backgroundColor: "#fef2f2",
          border: "1px solid #fecaca",
          borderRadius: "4px",
          marginBottom: "12px",
        }}>
          <div style={{ display: "flex", alignItems: "flex-start", gap: "8px" }}>
            <AlertTriangle size={18} style={{ color: "#dc2626", marginTop: "2px", flexShrink: 0 }} />
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, color: "#dc2626", marginBottom: "4px" }}>
                {section} failed to render
              </div>
              {isDev && this.state.error && (
                <details style={{ marginBottom: "8px" }}>
                  <summary style={{ cursor: "pointer", color: "#7f1d1d", fontSize: "12px" }}>
                    Error details
                  </summary>
                  <pre style={{
                    backgroundColor: "#fff7ed",
                    padding: "8px",
                    borderRadius: "2px",
                    fontSize: "11px",
                    overflow: "auto",
                    maxHeight: "200px",
                    marginTop: "4px",
                  }}>
                    {this.state.error.toString()}
                    {this.state.errorInfo?.componentStack && (
                      <>
                        {"\n\n"}
                        {this.state.errorInfo.componentStack}
                      </>
                    )}
                  </pre>
                </details>
              )}
              <button
                onClick={this.handleRetry}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "4px",
                  padding: "6px 12px",
                  backgroundColor: "#dc2626",
                  color: "white",
                  border: "none",
                  borderRadius: "4px",
                  cursor: "pointer",
                  fontSize: "12px",
                  fontWeight: 500,
                }}
              >
                <RefreshCw size={14} />
                Try Again
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default DataSectionErrorBoundary;
