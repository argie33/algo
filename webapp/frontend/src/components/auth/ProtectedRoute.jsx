import { Navigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';

function ProtectedRoute({ children, requireAuth = false, requireRole = null }) {
  const { isAuthenticated, isLoading, user } = useAuth();

  // Show loading state while checking auth
  if (isLoading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>
        <div>Loading...</div>
      </div>
    );
  }

  // Check if auth is required but user is not authenticated
  if (requireAuth && !isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  // Check role requirement
  if (requireRole && isAuthenticated) {
    if (user?.role !== requireRole) {
      // User doesn't have required role - redirect to markets (public page)
      return <Navigate to="/app/markets" replace />;
    }
  }

  return children;
}

export default ProtectedRoute;
