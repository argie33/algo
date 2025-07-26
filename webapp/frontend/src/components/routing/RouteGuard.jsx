import React from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { useNavigation } from '../../contexts/NavigationContext';
import { isProtectedRoute } from '../../routing/routeConfig';
import LoadingTransition from '../LoadingTransition';
import AuthRequiredMessage from './AuthRequiredMessage';

/**
 * RouteGuard - Unified route protection component
 * 
 * Handles authentication requirements for all routes in a consistent manner.
 * Replaces SmartRouting and other authentication checking components.
 */
const RouteGuard = ({ children, path }) => {
  const { isAuthenticated, isLoading, user } = useAuth();
  const { openAuthModal } = useNavigation();

  // Show loading while checking authentication
  if (isLoading) {
    return (
      <LoadingTransition 
        message="Checking authentication..."
        submessage="Please wait while we verify your session"
        type="auth"
      />
    );
  }

  // Check if route requires authentication
  const requiresAuth = isProtectedRoute(path);

  if (requiresAuth && !isAuthenticated) {
    // Show auth required message for protected routes
    return (
      <AuthRequiredMessage 
        requiredFor={path}
        onSignInClick={openAuthModal}
      />
    );
  }

  // Render the protected content
  return children;
};

export default RouteGuard;