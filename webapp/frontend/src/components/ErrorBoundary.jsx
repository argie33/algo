import React from "react";
import {
  Box,
  Typography,
  Button,
  Card,
  CardContent,
  Alert,
  Divider,
  Stack,
  Tooltip,
} from "@mui/material";
import {
  ErrorOutline,
  Refresh,
  Home,
  ContactSupport,
  ContentCopy,
  CheckCircle,
} from "@mui/icons-material";

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      errorId: null,
      copiedToClipboard: false,
    };
    // variant can be 'page' (full MUI UI) or 'form' (minimal UI) or undefined (defaults to 'page')
    this.variant = props.variant || "page";
  }

  static getDerivedStateFromError(_error) {
    // Update state so the next render will show the fallback UI
    return {
      hasError: true,
      errorId: `ERR_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    };
  }

  componentDidCatch(error, errorInfo) {
    // ALWAYS capture and display React rendering errors
    // Development: Show full error details for debugging
    // Production: Show user-friendly message but log full details

    const isDev = process.env.NODE_ENV !== "production";

    // Log the error to console for debugging
    console.error("❌ ErrorBoundary caught an error:");
    console.error("Error message:", error?.message);
    console.error("Error name:", error?.name);
    console.error("Component stack:", errorInfo?.componentStack);
    console.error("Full error:", error);

    // Enhanced logging for null reference errors
    if (
      error &&
      error.message &&
      (error.message.includes("Cannot read properties of undefined") ||
        error.message.includes("Cannot read property") ||
        error.message.includes("is not a function") ||
        error.message.includes("is not defined"))
    ) {
      console.error("🔴 CRITICAL: Property access on undefined/null");
      console.error(
        "This usually means a component tried to render data that doesn't exist."
      );
      console.error("Check that API responses have the expected structure.");
      if (errorInfo?.componentStack) {
        const firstComponent = errorInfo.componentStack.split("\n")[0];
        console.error("Component that failed:", firstComponent);
      }
    }

    // ALWAYS set state to show error UI
    this.setState({
      error: error,
      errorInfo: errorInfo,
    });

    // In production, you would send this to an error reporting service
    // like Sentry, LogRocket, or Bugsnag
    if (!isDev) {
      // Example: Send to error reporting service
      // errorReportingService.captureException(error, {
      //   extra: errorInfo,
      //   tags: {
      //     component: 'ErrorBoundary'
      //   }
      // });
    }
  }

  handleReload = () => {
    // Clear the error state and reload the component
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
      errorId: null,
    });

    // Reload the entire page to ensure clean state
    window.location.reload();
  };

  handleGoHome = () => {
    window.location.href = "/";
  };

  handleCopyErrorId = async () => {
    try {
      await navigator.clipboard.writeText(this.state.errorId);
      this.setState({ copiedToClipboard: true });
      setTimeout(() => {
        this.setState({ copiedToClipboard: false });
      }, 2000);
    } catch (err) {
      console.error("Failed to copy error ID:", err);
    }
  };

  getErrorSummary = () => {
    const error = this.state.error;
    if (!error) return "An unexpected error occurred";

    const msg = error?.message || "";
    if (msg.includes("Cannot read") || msg.includes("Cannot access")) {
      return "Data structure error - the application received unexpected data format. This may indicate incomplete data from the server.";
    } else if (msg.includes("is not a function")) {
      return "Function error - the application tried to call a non-existent function";
    } else if (msg.includes("Network") || msg.includes("ECONNREFUSED")) {
      return "Network error - unable to communicate with the server";
    } else if (msg.includes("timeout")) {
      return "Request timeout - the server took too long to respond";
    } else if (msg.includes("null")) {
      return "Missing data error - the application tried to process null or undefined data";
    }
    return msg || "An unexpected error occurred";
  };

  static reportApiError = (errorInfo) => {
    // Static method to allow components to report API errors
    // Used by components that catch API errors from useApiQuery
    const errorId = `ERR_API_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    console.error(`[API Error ${errorId}]`, errorInfo);

    // Optionally: Create a global error event that a parent ErrorBoundary could catch
    if (typeof window !== "undefined") {
      window.dispatchEvent(
        new CustomEvent("apiError", {
          detail: { ...errorInfo, errorId },
        })
      );
    }

    return errorId;
  };

  renderPageVariant() {
    return (
      <Box
        sx={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          bgcolor: "grey.50",
          p: 3,
        }}
      >
        <Card sx={{ maxWidth: 600, width: "100%" }}>
          <CardContent sx={{ p: 4 }}>
            <Stack spacing={3} alignItems="center" textAlign="center">
              {/* Error Icon */}
              <ErrorOutline
                data-testid="ErrorOutlineIcon"
                sx={{ fontSize: 64, color: "error.main" }}
              />

              {/* Main Error Message */}
              <Box>
                <Typography variant="h4" fontWeight={700} gutterBottom>
                  Something went wrong
                </Typography>
                <Typography
                  variant="body1"
                  color="text.secondary"
                  sx={{ mb: 2 }}
                >
                  We apologize for the inconvenience. An unexpected error has
                  occurred in our financial dashboard application.
                </Typography>
              </Box>

              {/* Error Details for Development */}
              {process.env.NODE_ENV === "development" && this.state.error && (
                <Alert
                  severity="error"
                  sx={{ width: "100%", textAlign: "left" }}
                >
                  <Typography
                    variant="subtitle2"
                    fontWeight={600}
                    gutterBottom
                  >
                    Error Details (Development Only):
                  </Typography>
                  <Typography
                    variant="body2"
                    sx={{ fontFamily: "monospace", mb: 1 }}
                  >
                    {this.state.error.toString()}
                  </Typography>
                  {this.state.errorInfo?.componentStack && (
                    <details style={{ marginTop: 8 }}>
                      <summary style={{ cursor: "pointer", fontWeight: 600 }}>
                        Component Stack
                      </summary>
                      <pre
                        style={{
                          fontSize: "0.75rem",
                          marginTop: 8,
                          whiteSpace: "pre-wrap",
                          maxHeight: 200,
                          overflow: "auto",
                        }}
                      >
                        {this.state.errorInfo.componentStack}
                      </pre>
                    </details>
                  )}
                </Alert>
              )}

              {/* Error Details for Production */}
              {process.env.NODE_ENV === "production" && (
                <Alert severity="warning" sx={{ width: "100%" }}>
                  <Stack spacing={1}>
                    <Box>
                      <Typography variant="body2" gutterBottom>
                        <strong>Error Details:</strong>
                      </Typography>
                      <Typography variant="body2" sx={{ mb: 1 }}>
                        {this.getErrorSummary()}
                      </Typography>
                    </Box>
                    <Stack direction="row" spacing={1} alignItems="center">
                      <Box>
                        <Typography variant="caption" color="text.secondary">
                          Error ID: <code>{this.state.errorId}</code>
                        </Typography>
                      </Box>
                      <Tooltip
                        title={
                          this.state.copiedToClipboard
                            ? "Copied!"
                            : "Copy error ID"
                        }
                      >
                        <Button
                          size="small"
                          onClick={this.handleCopyErrorId}
                          variant="text"
                          startIcon={
                            this.state.copiedToClipboard ? (
                              <CheckCircle sx={{ fontSize: 16 }} />
                            ) : (
                              <ContentCopy sx={{ fontSize: 16 }} />
                            )
                          }
                        >
                          {this.state.copiedToClipboard ? "Copied" : "Copy"}
                        </Button>
                      </Tooltip>
                    </Stack>
                    <Typography variant="caption" color="text.secondary">
                      Please provide the error ID above when contacting
                      support for faster assistance.
                    </Typography>
                  </Stack>
                </Alert>
              )}

              <Divider sx={{ width: "100%" }} />

              {/* Action Buttons */}
              <Stack direction="row" spacing={2}>
                <Button
                  variant="contained"
                  startIcon={<Refresh />}
                  onClick={this.handleReload}
                  size="large"
                >
                  Try Again
                </Button>
                <Button
                  variant="outlined"
                  startIcon={<Home />}
                  onClick={this.handleGoHome}
                  size="large"
                >
                  Go Home
                </Button>
              </Stack>

              {/* Support Information */}
              <Box sx={{ mt: 2 }}>
                <Typography
                  variant="body2"
                  color="text.secondary"
                  gutterBottom
                >
                  If this problem persists, please contact our support team:
                </Typography>
                <Button
                  variant="text"
                  startIcon={<ContactSupport />}
                  size="small"
                  href="mailto:support@edgebrooke.com"
                >
                  support@edgebrooke.com
                </Button>
              </Box>

              {/* Professional Footer */}
              <Box
                sx={{
                  mt: 3,
                  pt: 2,
                  borderTop: 1,
                  borderColor: "divider",
                  width: "100%",
                }}
              >
                <Typography
                  variant="caption"
                  color="text.secondary"
                  textAlign="center"
                >
                  Edgebrooke Capital Financial Dashboard
                  <br />
                  Enterprise-grade financial data platform for professional
                  investors
                </Typography>
              </Box>
            </Stack>
          </CardContent>
        </Card>
      </Box>
    );
  }

  renderFormVariant() {
    return (
      <div
        className="alert alert-danger"
        style={{ marginBottom: "var(--space-4)" }}
      >
        <div style={{ marginBottom: "var(--space-3)" }}>
          <strong>Form submission failed</strong>
          <p style={{ marginTop: "var(--space-2)", fontSize: "var(--t-sm)" }}>
            {this.state.error?.message || "An unexpected error occurred"}
          </p>
          {this.state.errorInfo && (
            <details
              style={{
                marginTop: "var(--space-2)",
                fontSize: "var(--t-2xs)",
              }}
            >
              <summary style={{ cursor: "pointer", fontWeight: "var(--w-bold)" }}>
                Details
              </summary>
              <pre
                style={{
                  marginTop: "var(--space-2)",
                  padding: "var(--space-2)",
                  background: "var(--surface)",
                  borderRadius: "var(--r-sm)",
                  overflow: "auto",
                }}
              >
                {this.state.errorInfo.componentStack}
              </pre>
            </details>
          )}
        </div>
        <button
          type="button"
          className="btn btn-sm btn-default"
          onClick={this.handleReload}
          style={{ marginTop: "var(--space-3)" }}
        >
          Try Again
        </button>
      </div>
    );
  }

  render() {
    if (this.state.hasError) {
      return this.variant === "form"
        ? this.renderFormVariant()
        : this.renderPageVariant();
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
