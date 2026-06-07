import { Navigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { isCognitoConfigured } from '../../config/amplify';

function ProtectedRoute({ children, requireAuth = false, requireRole = null }) {
  const { isAuthenticated, isLoading, user } = useAuth();
  const cognitoConfigured = isCognitoConfigured();
  const isDev = import.meta.env.DEV;

  // Show loading state while checking auth
  if (isLoading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>
        <div>Loading...</div>
      </div>
    );
  }

  // In development mode, allow access to protected routes even without authentication
  // This enables dev/testing workflows without requiring Cognito login
  if (isDev && !isAuthenticated && !cognitoConfigured) {
    // Dev mode without Cognito - AuthContext provides dev tokens automatically
    if (requireRole && user?.role !== requireRole) {
      return <Navigate to="/app" replace />;
    }
    return children;
  }

  // In development mode with Cognito configured but no active session, provide fallback access
  // This prevents blocking dev workflows when Cognito is configured but user isn't logged in
  if (isDev && requireAuth && !isAuthenticated && cognitoConfigured) {
    // Use dev tokens for development
    // Check role requirement
    if (requireRole && (!user || user.role !== requireRole)) {
      return <Navigate to="/app" replace />;
    }
    // Allow access with fallback dev authentication
    return children;
  }

  // Production behavior: require authentication when Cognito is configured
  if (requireAuth && !isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  // Check role requirement when authenticated
  if (requireRole && isAuthenticated) {
    if (user?.role !== requireRole) {
      return <Navigate to="/app" replace />;
    }
  }

  return children;
}

export default ProtectedRoute;

