import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

/**
 * LoginRedirect Component
 * 
 * Redirects /login URL to open the same sign-in modal as the header button.
 * This ensures a consistent experience - no separate login page.
 */
const LoginRedirect = ({ onSignInClick }) => {
  const navigate = useNavigate();
  const { isAuthenticated } = useAuth();

  useEffect(() => {
    if (isAuthenticated) {
      // If already authenticated, go to dashboard
      navigate('/dashboard', { replace: true });
    } else {
      // If not authenticated, go to dashboard and open the sign-in modal
      // This is EXACTLY what the header "Sign In" button does
      navigate('/dashboard', { replace: true });
      // Small delay to ensure navigation completes before opening modal
      setTimeout(() => {
        onSignInClick();
      }, 100);
    }
  }, [navigate, onSignInClick, isAuthenticated]);

  // Return null since this component only handles the redirect
  return null;
};

export default LoginRedirect;