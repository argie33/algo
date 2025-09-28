import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import MarketOverview from '../pages/MarketOverview';

/**
 * RootRedirect Component
 * Handles routing logic for the root path (/)
 * - If authenticated: Shows MarketOverview (default landing page)
 * - If not authenticated: Shows MarketOverview (public access)
 * - Dashboard is accessible via /dashboard for authenticated users only
 */
const RootRedirect = () => {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();

  // For now, both authenticated and unauthenticated users see Market Overview at root
  // Dashboard is accessed via /dashboard and is protected
  return <MarketOverview />;
};

export default RootRedirect;