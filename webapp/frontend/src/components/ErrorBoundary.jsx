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
} from "@mui/material";
import {
  ErrorOutline,
  Refresh,
  Home,
  ContactSupport,
} from "@mui/icons-material";

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      errorId: null,
    };
  }

  static getDerivedStateFromError(_error) {
    // Update state so the next render will show the fallback UI
    return {
      hasError: true,
      errorId: `ERR_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    };
  }

  componentDidCatch(error, errorInfo) {
    // Only catch React rendering errors, not API/async errors
    const isReactRenderError = errorInfo && errorInfo.componentStack;
    const isNetworkError =
      error &&
      error.message &&
      (error.message.includes("Network Error") ||
        error.message.includes("fetch") ||
        error.message.includes("ECONNREFUSED") ||
        error.message.includes("timeout"));

    // Don't catch network/API errors - let components handle them
    if (isNetworkError && !isReactRenderError) {
      console.warn(
        "API/Network error caught by ErrorBoundary, but not showing error UI:",
        error
      );
      return;
    }

    // Log the error to our error reporting service
    console.error(
      "ErrorBoundary caught a React render error:",
      error,
      errorInfo
    );

    this.setState({
      error: error,
      errorInfo: errorInfo,
    });

    // In production, you would send this to an error reporting service
    // like Sentry, LogRocket, or Bugsnag
    if (process.env.NODE_ENV === "production") {
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

  render() {
    if (this.state.hasError) {
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

                {/* Error ID for Production */}
                {process.env.NODE_ENV === "production" && (
                  <Alert severity="info" sx={{ width: "100%" }}>
                    <Typography variant="body2">
                      <strong>Error ID:</strong> {this.state.errorId}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      Please provide this ID when contacting support for faster
                      assistance.
                    </Typography>
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

    return this.props.children;
  }
}

export default ErrorBoundary;
