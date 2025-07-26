import React, { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import WelcomeLanding from '../pages/WelcomeLanding';
import Dashboard from '../pages/Dashboard';
import LoadingTransition from './LoadingTransition';

const SmartRouting = ({ onSignInClick }) => {
  const { isAuthenticated, user, isLoading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [loadingTimeout, setLoadingTimeout] = useState(false);

  // Prevent infinite loading - timeout after 10 seconds
  useEffect(() => {
    if (isLoading) {
      const timeout = setTimeout(() => {
        console.warn('⚠️ SmartRouting loading timeout - forcing fallback');
        setLoadingTimeout(true);
      }, 10000);
      
      return () => clearTimeout(timeout);
    } else {
      setLoadingTimeout(false);
    }
  }, [isLoading]);

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

  // Show loading while checking authentication (with timeout fallback)
  if (isLoading && !loadingTimeout) {
    return (
      <LoadingTransition 
        message="Loading dashboard..."
        submessage="Please wait while we prepare your workspace"
        type="auth"
      />
    );
  }

  // If loading timed out, force show dashboard for authenticated users
  if (loadingTimeout && isAuthenticated) {
    console.warn('⚠️ Loading timeout - showing dashboard despite loading state');
    return <Dashboard />;
  }

  // Show appropriate content based on authentication status
  if (isAuthenticated && user) {
    return <Dashboard />;
  }

  // Show welcome landing for anonymous users
  return <WelcomeLanding onSignInClick={onSignInClick} />;
};

export default SmartRouting;