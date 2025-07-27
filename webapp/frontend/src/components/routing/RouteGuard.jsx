import React from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { useNavigation } from '../../contexts/NavigationContext';
import { isProtectedRoute } from '../../routing/routeConfig';
import LoadingTransition from '../LoadingTransition';
import AuthRequiredMessage from './AuthRequiredMessage';

/**
 * IMPROVED RouteGuard - Enhanced route protection with better UX
 * 
 * Handles authentication requirements with improved loading states and user feedback.
 * Prevents auth flicker and provides clear user guidance.
 */
const RouteGuard = ({ children, path }) => {
  const { isAuthenticated, isLoading, user, error, retryCount } = useAuth();
  const { openAuthModal, intendedPath } = useNavigation();

  // IMPROVED: Show different loading states based on context
  if (isLoading) {
    // Determine loading message based on auth state
    const isInitialLoad = retryCount === 0;
    const isRetrying = retryCount > 0;
    
    let message = "Checking authentication...";
    let submessage = "Please wait while we verify your session";
    
    if (isInitialLoad) {
      message = "Loading application...";
      submessage = "Initializing your session";
    } else if (isRetrying) {
      message = "Reconnecting...";
      submessage = `Attempting to restore your session (${retryCount}/3)`;
    }
    
    return (
      <LoadingTransition 
        message={message}
        submessage={submessage}
        type="auth"
      />
    );
  }

  // IMPROVED: Handle authentication errors gracefully
  if (error && !isAuthenticated) {
    return (
      <LoadingTransition 
        message="Authentication Error"
        submessage={error}
        type="error"
        showRetry={true}
        onRetry={() => window.location.reload()}
      />
    );
  }

  // Check if route requires authentication
  const requiresAuth = isProtectedRoute(path);

  if (requiresAuth && !isAuthenticated) {
    // IMPROVED: Check if this is the intended destination
    const isIntendedDestination = intendedPath === path;
    
    // Show auth required message for protected routes
    return (
      <AuthRequiredMessage 
        requiredFor={path}
        onSignInClick={openAuthModal}
        isIntendedDestination={isIntendedDestination}
        showContext={true}
      />
    );
  }

  // IMPROVED: Log successful access for debugging
  if (requiresAuth && isAuthenticated) {
    console.log(`✅ RouteGuard: Authorized access to ${path} for user ${user?.username}`);
  }

  // Render the protected content
  return children;
};

export default RouteGuard;