import { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export const usePostLoginFlow = () => {
  const { isAuthenticated, user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [showWelcomeMessage, setShowWelcomeMessage] = useState(false);
  const [isFirstTimeUser, setIsFirstTimeUser] = useState(false);

  useEffect(() => {
    if (isAuthenticated && user) {
      // Check if this is a first-time user
      const lastLogin = localStorage.getItem(`lastLogin_${user.userId}`);
      const isFirstTime = !lastLogin;
      
      setIsFirstTimeUser(isFirstTime);
      setShowWelcomeMessage(true);

      // Store current login timestamp
      localStorage.setItem(`lastLogin_${user.userId}`, new Date().toISOString());

      // Handle redirect logic
      const intendedPath = sessionStorage.getItem('intendedPath');
      sessionStorage.removeItem('intendedPath');

      if (intendedPath && intendedPath !== '/') {
        // Redirect to intended path with a slight delay to show welcome message
        const redirectTimer = setTimeout(() => {
          navigate(intendedPath, { replace: true });
        }, 2000);
        return () => clearTimeout(redirectTimer);
      } else if (location.pathname === '/' || location.pathname === '/market') {
        // Default redirect to dashboard for new sessions
        const redirectTimer = setTimeout(() => {
          navigate('/', { replace: true });
        }, 1500);
        return () => clearTimeout(redirectTimer);
      }
    }
  }, [isAuthenticated, user, navigate, location.pathname]);

  const dismissWelcomeMessage = () => {
    setShowWelcomeMessage(false);
  };

  return {
    showWelcomeMessage,
    isFirstTimeUser,
    dismissWelcomeMessage,
    user
  };
};

export default usePostLoginFlow;