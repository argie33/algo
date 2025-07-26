import React, { useState } from 'react';
import {
  Alert,
  AlertTitle,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Collapse,
  Divider,
  IconButton,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Paper,
  Typography,
  useTheme
} from '@mui/material';
import {
  Error as ErrorIcon,
  Warning as WarningIcon,
  Info as InfoIcon,
  ExpandMore,
  ExpandLess,
  Refresh,
  ContentCopy,
  CheckCircle,
  Settings,
  Build,
  BugReport
} from '@mui/icons-material';

/**
 * Comprehensive error display component for authentication issues
 * Shows clear, actionable error messages with troubleshooting steps
 */
function AuthErrorDisplay({ error, detailedError, diagnostics, onRetry, onClearError }) {
  const theme = useTheme();
  const [expanded, setExpanded] = useState(false);
  const [diagnosticsExpanded, setDiagnosticsExpanded] = useState(false);
  const [copiedToClipboard, setCopiedToClipboard] = useState(false);

  if (!error && !detailedError) return null;

  const getSeverityIcon = (severity) => {
    switch (severity) {
      case 'CRITICAL': return <ErrorIcon color="error" />;
      case 'HIGH': return <WarningIcon color="warning" />;
      default: return <InfoIcon color="info" />;
    }
  };

  const getSeverityColor = (severity) => {
    switch (severity) {
      case 'CRITICAL': return 'error';
      case 'HIGH': return 'warning';
      default: return 'info';
    }
  };

  const copyDiagnostics = async () => {
    if (!diagnostics) return;

    const diagnosticsText = JSON.stringify(diagnostics, null, 2);
    try {
      await navigator.clipboard.writeText(diagnosticsText);
      setCopiedToClipboard(true);
      setTimeout(() => setCopiedToClipboard(false), 2000);
    } catch (err) {
      console.error('Failed to copy diagnostics:', err);
    }
  };

  return (
    <Box sx={{ maxWidth: 800, mx: 'auto', p: 2 }}>
      {/* Main Error Alert */}
      <Alert 
        severity={detailedError?.type === 'CONFIGURATION_ERROR' ? 'error' : 'warning'}
        sx={{ mb: 2 }}
      >
        <AlertTitle>
          {detailedError?.title || 'Authentication Error'}
        </AlertTitle>
        
        <Typography variant="body2" sx={{ mb: 2 }}>
          {detailedError?.message || error}
        </Typography>

        {detailedError?.quickFix && (
          <Box sx={{ mb: 2 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 1 }}>
              Quick Fix:
            </Typography>
            <Typography variant="body2" sx={{ 
              backgroundColor: 'rgba(0, 0, 0, 0.04)',
              p: 1,
              borderRadius: 1,
              fontFamily: 'monospace'
            }}>
              {detailedError.quickFix}
            </Typography>
          </Box>
        )}

        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          {onRetry && (
            <Button
              size="small"
              startIcon={<Refresh />}
              onClick={onRetry}
              variant="outlined"
            >
              Retry
            </Button>
          )}
          
          <Button
            size="small"
            startIcon={expanded ? <ExpandLess /> : <ExpandMore />}
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? 'Hide Details' : 'Show Details'}
          </Button>

          {onClearError && (
            <Button
              size="small"
              onClick={onClearError}
              color="inherit"
            >
              Dismiss
            </Button>
          )}
        </Box>
      </Alert>

      {/* Detailed Error Information */}
      <Collapse in={expanded}>
        <Card sx={{ mb: 2 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              <BugReport sx={{ mr: 1, verticalAlign: 'middle' }} />
              Detailed Error Information
            </Typography>

            {detailedError && (
              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  Error Type: <Chip label={detailedError.type} size="small" />
                </Typography>
                
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  Timestamp: {new Date(detailedError.timestamp).toLocaleString()}
                </Typography>

                {detailedError.originalError && (
                  <Box sx={{ mt: 1 }}>
                    <Typography variant="subtitle2">Original Error:</Typography>
                    <Paper sx={{ p: 1, backgroundColor: '#f5f5f5', fontFamily: 'monospace', fontSize: '0.8em' }}>
                      {detailedError.originalError}
                    </Paper>
                  </Box>
                )}
              </Box>
            )}

            {/* Recommendations */}
            {detailedError?.recommendations && detailedError.recommendations.length > 0 && (
              <Box sx={{ mb: 2 }}>
                <Typography variant="h6" gutterBottom>
                  <Settings sx={{ mr: 1, verticalAlign: 'middle' }} />
                  Recommended Actions
                </Typography>
                
                {detailedError.recommendations.map((rec, index) => (
                  <Alert 
                    key={index}
                    severity={getSeverityColor(rec.priority)}
                    sx={{ mb: 1 }}
                  >
                    <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                      {getSeverityIcon(rec.priority)}
                      <Typography variant="subtitle2" sx={{ ml: 1, fontWeight: 'bold' }}>
                        {rec.issue}
                      </Typography>
                    </Box>
                    
                    <Typography variant="body2" sx={{ mb: 1 }}>
                      <strong>Solution:</strong> {rec.solution}
                    </Typography>
                    
                    <Box>
                      <Typography variant="body2" sx={{ fontWeight: 'bold', mb: 1 }}>
                        Steps to Fix:
                      </Typography>
                      <List dense>
                        {rec.steps.map((step, stepIndex) => (
                          <ListItem key={stepIndex} sx={{ py: 0 }}>
                            <ListItemIcon sx={{ minWidth: 36 }}>
                              <Build sx={{ fontSize: 16 }} />
                            </ListItemIcon>
                            <ListItemText 
                              primary={step}
                              primaryTypographyProps={{ variant: 'body2' }}
                            />
                          </ListItem>
                        ))}
                      </List>
                    </Box>
                  </Alert>
                ))}
              </Box>
            )}
          </CardContent>
        </Card>
      </Collapse>

      {/* Diagnostics Information */}
      {diagnostics && (
        <Card>
          <CardContent>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
              <Typography variant="h6">
                <InfoIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
                System Diagnostics
              </Typography>
              
              <Box>
                <IconButton
                  size="small"
                  onClick={copyDiagnostics}
                  title="Copy diagnostics to clipboard"
                >
                  {copiedToClipboard ? <CheckCircle color="success" /> : <ContentCopy />}
                </IconButton>
                
                <IconButton
                  size="small"
                  onClick={() => setDiagnosticsExpanded(!diagnosticsExpanded)}
                >
                  {diagnosticsExpanded ? <ExpandLess /> : <ExpandMore />}
                </IconButton>
              </Box>
            </Box>

            {/* Diagnostics Summary */}
            <Box sx={{ display: 'flex', gap: 2, mb: 2, flexWrap: 'wrap' }}>
              <Chip
                label={`Configuration Sources: ${Object.keys(diagnostics.configurationSources || {}).length}`}
                variant="outlined"
                size="small"
              />
              <Chip
                label={`Amplify: ${diagnostics.amplifyStatus?.configured ? 'Configured' : 'Not Configured'}`}
                color={diagnostics.amplifyStatus?.configured ? 'success' : 'error'}
                variant="outlined"
                size="small"
              />
              <Chip
                label={`API: ${diagnostics.apiConnectivity?.reachable ? 'Reachable' : 'Unreachable'}`}
                color={diagnostics.apiConnectivity?.reachable ? 'success' : 'error'}
                variant="outlined"
                size="small"
              />
            </Box>

            <Collapse in={diagnosticsExpanded}>
              {/* Configuration Sources Status */}
              <Box sx={{ mb: 2 }}>
                <Typography variant="subtitle2" gutterBottom>
                  Configuration Sources:
                </Typography>
                {Object.entries(diagnostics.configurationSources || {}).map(([source, data]) => (
                  <Alert 
                    key={source}
                    severity={data.valid ? 'success' : 'error'}
                    sx={{ mb: 1 }}
                  >
                    <Typography variant="body2" fontWeight="bold">
                      {source.charAt(0).toUpperCase() + source.slice(1)}
                    </Typography>
                    {data.errors && data.errors.slice(0, 3).map((error, index) => (
                      <Typography key={index} variant="body2" sx={{ fontSize: '0.8em' }}>
                        {error}
                      </Typography>
                    ))}
                  </Alert>
                ))}
              </Box>

              {/* System Information */}
              <Box sx={{ mb: 2 }}>
                <Typography variant="subtitle2" gutterBottom>
                  Environment Information:
                </Typography>
                <Paper sx={{ p: 2, backgroundColor: '#f8f9fa' }}>
                  <Typography variant="body2" gutterBottom>
                    <strong>URL:</strong> {diagnostics.environment?.url}
                  </Typography>
                  <Typography variant="body2" gutterBottom>
                    <strong>Environment:</strong> {diagnostics.environment?.nodeEnv}
                  </Typography>
                  <Typography variant="body2" gutterBottom>
                    <strong>Timestamp:</strong> {new Date(diagnostics.timestamp).toLocaleString()}
                  </Typography>
                </Paper>
              </Box>

              {/* All Recommendations */}
              {diagnostics.recommendations && diagnostics.recommendations.length > 0 && (
                <Box>
                  <Typography variant="subtitle2" gutterBottom>
                    All System Recommendations:
                  </Typography>
                  {diagnostics.recommendations.map((rec, index) => (
                    <Alert key={index} severity={getSeverityColor(rec.priority)} sx={{ mb: 1 }}>
                      <Typography variant="body2">
                        <strong>{rec.category}:</strong> {rec.issue} - {rec.solution}
                      </Typography>
                    </Alert>
                  ))}
                </Box>
              )}
            </Collapse>
          </CardContent>
        </Card>
      )}
    </Box>
  );
}

export default AuthErrorDisplay;