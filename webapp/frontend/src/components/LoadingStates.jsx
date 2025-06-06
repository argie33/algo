import React from 'react'
import {
  Box,
  Card,
  CardContent,
  Typography,
  CircularProgress,
  Alert,
  Button,
  useTheme
} from '@mui/material'
import { ErrorOutline, Refresh } from '@mui/icons-material'

// Loading component
export function LoadingCard({ message = "Loading..." }) {
  return (
    <Card>
      <CardContent>
        <Box 
          display="flex" 
          flexDirection="column" 
          alignItems="center" 
          justifyContent="center" 
          py={6}
        >
          <CircularProgress size={60} sx={{ mb: 2 }} />
          <Typography variant="h6" color="text.secondary">
            {message}
          </Typography>
        </Box>
      </CardContent>
    </Card>
  )
}

// Error component
export function ErrorCard({ 
  error, 
  onRetry, 
  title = "Something went wrong",
  showRetry = true 
}) {
  const theme = useTheme()

  return (
    <Card>
      <CardContent>
        <Box 
          display="flex" 
          flexDirection="column" 
          alignItems="center" 
          justifyContent="center" 
          py={6}
          textAlign="center"
        >
          <ErrorOutline 
            sx={{ 
              fontSize: 60, 
              color: theme.palette.error.main, 
              mb: 2 
            }} 
          />
          <Typography variant="h6" gutterBottom>
            {title}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            {error?.message || 'An unexpected error occurred. Please try again.'}
          </Typography>
          {showRetry && onRetry && (
            <Button
              variant="outlined"
              startIcon={<Refresh />}
              onClick={onRetry}
            >
              Try Again
            </Button>
          )}
        </Box>
      </CardContent>
    </Card>
  )
}

// No data component
export function NoDataCard({ 
  message = "No data available",
  description,
  action
}) {
  return (
    <Card>
      <CardContent>
        <Box 
          display="flex" 
          flexDirection="column" 
          alignItems="center" 
          justifyContent="center" 
          py={6}
          textAlign="center"
        >
          <Typography variant="h6" color="text.secondary" gutterBottom>
            {message}
          </Typography>
          {description && (
            <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              {description}
            </Typography>
          )}
          {action}
        </Box>
      </CardContent>
    </Card>
  )
}

// Page loading wrapper
export function PageLoading({ message = "Loading page..." }) {
  return (
    <Box 
      display="flex" 
      flexDirection="column" 
      alignItems="center" 
      justifyContent="center" 
      minHeight="60vh"
    >
      <CircularProgress size={60} sx={{ mb: 2 }} />
      <Typography variant="h6" color="text.secondary">
        {message}
      </Typography>
    </Box>
  )
}

// Inline loading for smaller components
export function InlineLoading({ size = 20, message }) {
  return (
    <Box display="flex" alignItems="center" gap={1}>
      <CircularProgress size={size} />
      {message && (
        <Typography variant="body2" color="text.secondary">
          {message}
        </Typography>
      )}
    </Box>
  )
}

// Error alert component
export function ErrorAlert({ error, onClose, severity = "error" }) {
  if (!error) return null

  return (
    <Alert 
      severity={severity} 
      onClose={onClose}
      sx={{ mb: 2 }}
    >
      {error.message || 'An error occurred'}
    </Alert>
  )
}

export default {
  LoadingCard,
  ErrorCard,
  NoDataCard,
  PageLoading,
  InlineLoading,
  ErrorAlert
}
