import React from 'react';
import { useNavigate } from 'react-router-dom';

/**
 * RootRedirect Component
 * Handles routing logic for the root path (/)
 * Redirects to Portfolio Holdings (admin default landing page)
 */
const RootRedirect = () => {
  const navigate = useNavigate();

  React.useEffect(() => {
    // Redirect to Portfolio Holdings
    navigate('/portfolio', { replace: true });
  }, [navigate]);

  return null;
};

export default RootRedirect;