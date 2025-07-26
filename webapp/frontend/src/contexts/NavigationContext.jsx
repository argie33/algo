import React, { createContext, useContext, useReducer, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from './AuthContext';
import { isPublicRoute, isProtectedRoute, getDefaultProtectedRoute } from '../routing/routeConfig';

// Navigation state
const initialState = {
  currentPath: '/',
  intendedPath: null,
  authModalOpen: false,
  isNavigating: false,
  navigationHistory: []
};

// Navigation actions
const NAV_ACTIONS = {
  SET_CURRENT_PATH: 'SET_CURRENT_PATH',
  SET_INTENDED_PATH: 'SET_INTENDED_PATH',
  CLEAR_INTENDED_PATH: 'CLEAR_INTENDED_PATH',
  OPEN_AUTH_MODAL: 'OPEN_AUTH_MODAL',
  CLOSE_AUTH_MODAL: 'CLOSE_AUTH_MODAL',
  SET_NAVIGATING: 'SET_NAVIGATING',
  ADD_TO_HISTORY: 'ADD_TO_HISTORY'
};

// Navigation reducer
function navigationReducer(state, action) {
  switch (action.type) {
    case NAV_ACTIONS.SET_CURRENT_PATH:
      return {
        ...state,
        currentPath: action.payload,
        navigationHistory: [...state.navigationHistory.slice(-9), action.payload]
      };
    case NAV_ACTIONS.SET_INTENDED_PATH:
      return {
        ...state,
        intendedPath: action.payload
      };
    case NAV_ACTIONS.CLEAR_INTENDED_PATH:
      return {
        ...state,
        intendedPath: null
      };
    case NAV_ACTIONS.OPEN_AUTH_MODAL:
      return {
        ...state,
        authModalOpen: true
      };
    case NAV_ACTIONS.CLOSE_AUTH_MODAL:
      return {
        ...state,
        authModalOpen: false
      };
    case NAV_ACTIONS.SET_NAVIGATING:
      return {
        ...state,
        isNavigating: action.payload
      };
    default:
      return state;
  }
}

// Create navigation context
const NavigationContext = createContext();

// Navigation provider component
export function NavigationProvider({ children }) {
  const [state, dispatch] = useReducer(navigationReducer, initialState);
  const { isAuthenticated, isLoading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  // Track current path changes
  useEffect(() => {
    dispatch({ type: NAV_ACTIONS.SET_CURRENT_PATH, payload: location.pathname });
  }, [location.pathname]);

  // Handle authentication-based navigation
  useEffect(() => {
    if (!isLoading) {
      handleAuthenticationNavigation();
    }
  }, [isAuthenticated, isLoading, location.pathname]);

  const handleAuthenticationNavigation = () => {
    const currentPath = location.pathname;
    
    if (isAuthenticated) {
      // User is authenticated
      if (state.intendedPath && isProtectedRoute(state.intendedPath)) {
        // Navigate to intended protected route
        navigate(state.intendedPath, { replace: true });
        dispatch({ type: NAV_ACTIONS.CLEAR_INTENDED_PATH });
      } else if (currentPath === '/login' || currentPath === '/welcome') {
        // Redirect auth pages to dashboard
        navigate(getDefaultProtectedRoute(), { replace: true });
      }
      // Close auth modal if open
      if (state.authModalOpen) {
        dispatch({ type: NAV_ACTIONS.CLOSE_AUTH_MODAL });
      }
    } else {
      // User is not authenticated
      if (isProtectedRoute(currentPath)) {
        // Store intended path and show auth requirement
        dispatch({ type: NAV_ACTIONS.SET_INTENDED_PATH, payload: currentPath });
        
        if (isPublicRoute('/')) {
          // Redirect to public home page
          navigate('/', { replace: true });
          // Open auth modal for protected route access
          dispatch({ type: NAV_ACTIONS.OPEN_AUTH_MODAL });
        }
      }
    }
  };

  // Navigation methods
  const navigateTo = (path, options = {}) => {
    if (isProtectedRoute(path) && !isAuthenticated) {
      // Store intended path and open auth modal
      dispatch({ type: NAV_ACTIONS.SET_INTENDED_PATH, payload: path });
      dispatch({ type: NAV_ACTIONS.OPEN_AUTH_MODAL });
      return;
    }

    // Direct navigation for public routes or authenticated users
    navigate(path, options);
  };

  const openAuthModal = () => {
    dispatch({ type: NAV_ACTIONS.OPEN_AUTH_MODAL });
  };

  const closeAuthModal = () => {
    dispatch({ type: NAV_ACTIONS.CLOSE_AUTH_MODAL });
  };

  const clearIntendedPath = () => {
    dispatch({ type: NAV_ACTIONS.CLEAR_INTENDED_PATH });
  };

  const handleSignInSuccess = () => {
    // Auth successful - navigation will be handled by useEffect
    console.log('🎉 Sign in successful - navigation will handle redirect');
  };

  const handleSpecialRoute = (routePath) => {
    switch (routePath) {
      case '/login':
        if (isAuthenticated) {
          navigate(getDefaultProtectedRoute(), { replace: true });
        } else {
          navigate('/', { replace: true });
          openAuthModal();
        }
        break;
      case '/logout':
        // Logout will be handled by auth context
        navigate('/', { replace: true });
        break;
      default:
        // Regular navigation
        navigateTo(routePath);
    }
  };

  const value = {
    // State
    currentPath: state.currentPath,
    intendedPath: state.intendedPath,
    authModalOpen: state.authModalOpen,
    isNavigating: state.isNavigating,
    navigationHistory: state.navigationHistory,
    
    // Methods
    navigateTo,
    openAuthModal,
    closeAuthModal,
    clearIntendedPath,
    handleSignInSuccess,
    handleSpecialRoute
  };

  return (
    <NavigationContext.Provider value={value}>
      {children}
    </NavigationContext.Provider>
  );
}

// Custom hook to use navigation context
export function useNavigation() {
  const context = useContext(NavigationContext);
  if (context === undefined) {
    throw new Error('useNavigation must be used within a NavigationProvider');
  }
  return context;
}

export default NavigationContext;