import React, { useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import WelcomeLanding from '../pages/WelcomeLanding';
import Dashboard from '../pages/Dashboard';
import LoadingTransition from './LoadingTransition';

const SmartRouting = ({ onSignInClick }) => {
  const { isAuthenticated, user, isLoading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  // Handle post-login redirect logic
  useEffect(() => {
    if (isAuthenticated && user && !isLoading) {
      // Get the path user was trying to access before login
      const intendedPath = sessionStorage.getItem('intendedPath');
      
      if (intendedPath && intendedPath !== '/') {
        // Clear the intended path and redirect
        sessionStorage.removeItem('intendedPath');
        navigate(intendedPath, { replace: true });
      } else {
        // Default redirect to dashboard for successful login
        navigate('/', { replace: true });
      }
    }
  }, [isAuthenticated, user, isLoading, navigate]);

  // Store intended path for post-login redirect
  useEffect(() => {
    if (!isAuthenticated && location.pathname !== '/' && location.pathname !== '/market') {
      sessionStorage.setItem('intendedPath', location.pathname);
    }
  }, [isAuthenticated, location.pathname]);

  // Show loading while checking authentication
  if (isLoading) {
    return (
      <LoadingTransition 
        message="Checking authentication..."
        submessage="Verifying your session and preparing your dashboard"
        type="auth"
      />
    );
  }

  // Show appropriate content based on authentication status
  if (isAuthenticated && user) {
    return <Dashboard />;
  }

  // Show welcome landing for anonymous users
  return <WelcomeLanding onSignInClick={onSignInClick} />;
};

export default SmartRouting;