import React, { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import WelcomeLanding from '../pages/WelcomeLanding';
import Dashboard from '../pages/Dashboard';
import LoadingTransition from './LoadingTransition';

const SmartRouting = ({ onSignInClick }) => {
  const { isAuthenticated, user, isLoading, retryCount, maxRetries, circuitBreakerOpen } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [loadingTimeout, setLoadingTimeout] = useState(false);
  const [authStateVersion, setAuthStateVersion] = useState(0);

  // Track auth state changes for better synchronization
  useEffect(() => {
    setAuthStateVersion(prev => prev + 1);
  }, [isAuthenticated, user?.sub, circuitBreakerOpen]);

  // Prevent infinite loading - reduced timeout with better fallback
  useEffect(() => {
    if (isLoading && !circuitBreakerOpen) {
      const timeout = setTimeout(() => {
        console.warn('⚠️ SmartRouting loading timeout - auth state may be stuck');
        console.warn(`Auth state: authenticated=${isAuthenticated}, retries=${retryCount}/${maxRetries}, circuitOpen=${circuitBreakerOpen}`);
        setLoadingTimeout(true);
      }, 5000); // Reduced from 10 seconds
      
      return () => clearTimeout(timeout);
    } else {
      setLoadingTimeout(false);
    }
  }, [isLoading, circuitBreakerOpen, isAuthenticated, retryCount, maxRetries]);

  // Handle post-login redirect logic
  useEffect(() => {
    if (isAuthenticated && user && !isLoading) {
      // Get the path user was trying to access before login
      const intendedPath = sessionStorage.getItem('intendedPath');
      
      if (intendedPath && intendedPath !== '/' && intendedPath !== '/dashboard') {
        // Clear the intended path and redirect
        sessionStorage.removeItem('intendedPath');
        navigate(intendedPath, { replace: true });
      }
      // If no intended path, we stay on dashboard (which is what this component renders)
    }
  }, [isAuthenticated, user, isLoading, navigate]);

  // Store intended path for post-login redirect
  useEffect(() => {
    if (!isAuthenticated && location.pathname !== '/' && location.pathname !== '/market') {
      sessionStorage.setItem('intendedPath', location.pathname);
    }
  }, [isAuthenticated, location.pathname]);

  // Handle circuit breaker state
  if (circuitBreakerOpen) {
    console.warn('🔴 Circuit breaker open - showing welcome page with error state');
    return <WelcomeLanding onSignInClick={onSignInClick} authError="Authentication service temporarily unavailable" />;
  }

  // Show loading while checking authentication (with improved timeout handling)
  if (isLoading && !loadingTimeout && retryCount < maxRetries) {
    return (
      <LoadingTransition 
        message="Verifying authentication..."
        submessage={retryCount > 0 ? `Retry attempt ${retryCount}/${maxRetries}` : "Please wait while we verify your session"}
        type="auth"
      />
    );
  }

  // If loading timed out or max retries reached, handle gracefully
  if (loadingTimeout || (isLoading && retryCount >= maxRetries)) {
    console.warn(`⚠️ Auth resolution timeout/failed - state: authenticated=${isAuthenticated}, user=${!!user}`);
    
    if (isAuthenticated && user) {
      console.warn('⚠️ Showing dashboard despite auth timeout (user appears authenticated)');
      return <Dashboard />;
    } else {
      console.warn('⚠️ Showing welcome page due to auth timeout (user not authenticated)');
      return <WelcomeLanding onSignInClick={onSignInClick} authError="Authentication verification timed out" />;
    }
  }

  // Show appropriate content based on authentication status
  if (isAuthenticated && user) {
    return <Dashboard />;
  }

  // Show welcome landing for anonymous users
  return <WelcomeLanding onSignInClick={onSignInClick} />;
};

export default SmartRouting;