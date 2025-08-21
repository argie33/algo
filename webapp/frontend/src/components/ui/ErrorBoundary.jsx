import React from "react";
import {
  Alert,
  AlertTitle,
  Box,
  Button,
  Typography,
  Collapse,
  IconButton,
  Paper,
} from "@mui/material";
import {
  Refresh,
  ExpandMore,
  ExpandLess,
  BugReport,
  Home,
} from "@mui/icons-material";
import { useNavigate } from "react-router-dom";

// Standardized Error Display Component
export const ErrorDisplay = ({
  error,
  title = "Something went wrong",
  onRetry,
  showDetails = true,
  severity = "error",
  fullPage = false,
}) => {
  const [showErrorDetails, setShowErrorDetails] = React.useState(false);
  const navigate = useNavigate();

  const errorMessage =
    error?.message || error?.toString() || "Unknown error occurred";
  const errorStack = error?.stack;
  const errorContext = error?.context || {};

  const logger = {
    error: (message, error, context) => {
      console.error(`[ErrorDisplay] ${message}`, {
        error: error?.message || error,
        stack: error?.stack,
        context,
      });
    },
  };

  React.useEffect(() => {
    logger.error("Error displayed to user", error, {
      title,
      severity,
      fullPage,
      errorContext,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [error, title, severity, fullPage]);

  const ErrorContent = () => (
    <>
      <Alert
        severity={severity}
        sx={{ mb: showErrorDetails ? 2 : 0 }}
        action={
          <Box display="flex" gap={1}>
            {showDetails && (
              <IconButton
                size="small"
                onClick={() => setShowErrorDetails(!showErrorDetails)}
                aria-label="Toggle error details"
              >
                {showErrorDetails ? <ExpandLess /> : <ExpandMore />}
              </IconButton>
            )}
            {onRetry && (
              <Button
                size="small"
                startIcon={<Refresh />}
                onClick={onRetry}
                variant="outlined"
                color={severity}
              >
                Retry
              </Button>
            )}
          </Box>
        }
      >
        <AlertTitle>{title}</AlertTitle>
        <Typography variant="body2">{errorMessage}</Typography>

        {fullPage && (
          <Box sx={{ mt: 2, display: "flex", gap: 1 }}>
            <Button
              size="small"
              startIcon={<Home />}
              onClick={() => navigate("/")}
              variant="outlined"
            >
              Go Home
            </Button>
            {onRetry && (
              <Button
                size="small"
                startIcon={<Refresh />}
                onClick={onRetry}
                variant="contained"
                color={severity}
              >
                Try Again
              </Button>
            )}
          </Box>
        )}
      </Alert>

      {showDetails && (
        <Collapse in={showErrorDetails}>
          <Paper variant="outlined" sx={{ p: 2, bgcolor: "grey.50" }}>
            <Typography variant="subtitle2" gutterBottom>
              <BugReport
                fontSize="small"
                sx={{ mr: 1, verticalAlign: "middle" }}
              />
              Error Details
            </Typography>

            <Box sx={{ mb: 2 }}>
              <Typography variant="caption" color="text.secondary">
                Message:
              </Typography>
              <Typography
                variant="body2"
                sx={{ fontFamily: "monospace", fontSize: "0.75rem" }}
              >
                {errorMessage}
              </Typography>
            </Box>

            {Object.keys(errorContext).length > 0 && (
              <Box sx={{ mb: 2 }}>
                <Typography variant="caption" color="text.secondary">
                  Context:
                </Typography>
                <Typography
                  variant="body2"
                  sx={{ fontFamily: "monospace", fontSize: "0.75rem" }}
                >
                  {JSON.stringify(errorContext, null, 2)}
                </Typography>
              </Box>
            )}

            {errorStack && (
              <Box>
                <Typography variant="caption" color="text.secondary">
                  Stack Trace:
                </Typography>
                <Typography
                  variant="body2"
                  sx={{
                    fontFamily: "monospace",
                    fontSize: "0.65rem",
                    maxHeight: 200,
                    overflow: "auto",
                    whiteSpace: "pre-wrap",
                  }}
                >
                  {errorStack}
                </Typography>
              </Box>
            )}

            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ mt: 1, display: "block" }}
            >
              Timestamp: {new Date().toISOString()}
            </Typography>
          </Paper>
        </Collapse>
      )}
    </>
  );

  if (fullPage) {
    return (
      <Box
        display="flex"
        justifyContent="center"
        alignItems="center"
        minHeight="60vh"
        p={3}
      >
        <Box maxWidth={600} width="100%">
          <ErrorContent />
        </Box>
      </Box>
    );
  }

  return <ErrorContent />;
};

// Standardized Loading Component
export const LoadingDisplay = ({
  message = "Loading...",
  fullPage = false,
  size = "medium",
}) => {
  const sizeMap = {
    small: 40,
    medium: 60,
    large: 80,
  };

  const LoadingContent = () => (
    <Box display="flex" flexDirection="column" alignItems="center" gap={2}>
      <Box
        sx={{
          width: sizeMap[size],
          height: sizeMap[size],
          border: "4px solid",
          borderColor: "primary.light",
          borderTopColor: "primary.main",
          borderRadius: "50%",
          animation: "spin 1s linear infinite",
          "@keyframes spin": {
            "0%": { transform: "rotate(0deg)" },
            "100%": { transform: "rotate(360deg)" },
          },
        }}
      />
      <Typography variant="h6" color="text.secondary">
        {message}
      </Typography>
    </Box>
  );

  if (fullPage) {
    return (
      <Box
        display="flex"
        justifyContent="center"
        alignItems="center"
        minHeight="60vh"
      >
        <LoadingContent />
      </Box>
    );
  }

  return (
    <Box sx={{ py: 4, textAlign: "center" }}>
      <LoadingContent />
    </Box>
  );
};

// Hook for consistent API error handling
// eslint-disable-next-line react-refresh/only-export-components
export const useStandardizedError = () => {
  const logger = {
    error: (message, error, context) => {
      console.error(`[useStandardizedError] ${message}`, {
        error: error?.message || error,
        stack: error?.stack,
        context,
      });
    },
  };

  const handleApiError = (error, context = {}) => {
    logger.error("API Error occurred", error, context);

    // Enhance error with context for better debugging
    const enhancedError = {
      ...error,
      context: {
        ...context,
        timestamp: new Date().toISOString(),
        userAgent: navigator.userAgent,
        url: window.location.href,
      },
    };

    return enhancedError;
  };

  const formatApiError = (error) => {
    if (error?.response?.status) {
      const status = error.response.status;
      if (status === 401)
        return "Authentication required. Please log in again.";
      if (status === 403)
        return "You don't have permission to access this resource.";
      if (status === 404) return "The requested resource was not found.";
      if (status === 500) return "Server error. Please try again later.";
      if (status >= 500)
        return "Service temporarily unavailable. Please try again.";
    }

    if (error?.message?.includes("fetch")) {
      return "Network error. Please check your connection and try again.";
    }

    return error?.message || "An unexpected error occurred.";
  };

  return {
    handleApiError,
    formatApiError,
  };
};

export default ErrorDisplay;
