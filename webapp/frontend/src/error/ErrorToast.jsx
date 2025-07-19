/**
 * ErrorToast - Toast notification system for errors
 * Provides non-intrusive error notifications with actions
 */

import React, { useState, useEffect } from 'react';
import errorManager from './ErrorManager';

const Toast = ({ error, onDismiss, onRetry, onDetails }) => {
  const [isVisible, setIsVisible] = useState(true);
  const [progress, setProgress] = useState(100);

  useEffect(() => {
    // Auto-dismiss after 5 seconds for low severity errors
    if (error.severity === errorManager.SEVERITY.LOW) {
      const duration = 5000;
      const interval = 50;
      const step = (interval / duration) * 100;

      const timer = setInterval(() => {
        setProgress(prev => {
          const newProgress = prev - step;
          if (newProgress <= 0) {
            clearInterval(timer);
            setIsVisible(false);
            setTimeout(onDismiss, 300); // Allow fade animation
            return 0;
          }
          return newProgress;
        });
      }, interval);

      return () => clearInterval(timer);
    }
  }, [error.severity, onDismiss]);

  const getToastStyles = () => {
    const baseStyles = "relative overflow-hidden transform transition-all duration-300 ease-in-out";
    
    if (!isVisible) {
      return `${baseStyles} translate-x-full opacity-0`;
    }

    switch (error.severity) {
      case errorManager.SEVERITY.CRITICAL:
        return `${baseStyles} bg-red-600 border-red-700 text-white`;
      case errorManager.SEVERITY.HIGH:
        return `${baseStyles} bg-red-50 border-red-200 text-red-800`;
      case errorManager.SEVERITY.MEDIUM:
        return `${baseStyles} bg-yellow-50 border-yellow-200 text-yellow-800`;
      case errorManager.SEVERITY.LOW:
        return `${baseStyles} bg-blue-50 border-blue-200 text-blue-800`;
      default:
        return `${baseStyles} bg-gray-50 border-gray-200 text-gray-800`;
    }
  };

  const getIcon = () => {
    switch (error.severity) {
      case errorManager.SEVERITY.CRITICAL:
        return '🚨';
      case errorManager.SEVERITY.HIGH:
        return '❌';
      case errorManager.SEVERITY.MEDIUM:
        return '⚠️';
      case errorManager.SEVERITY.LOW:
        return 'ℹ️';
      default:
        return '📝';
    }
  };

  const getUserFriendlyMessage = () => {
    // Map technical errors to user-friendly messages
    const message = error.message.toLowerCase();
    
    if (message.includes('network') || message.includes('fetch')) {
      return 'Connection issue - please check your internet';
    }
    if (message.includes('unauthorized') || message.includes('401')) {
      return 'Please sign in to continue';
    }
    if (message.includes('forbidden') || message.includes('403')) {
      return 'You don\'t have permission for this action';
    }
    if (message.includes('not found') || message.includes('404')) {
      return 'The requested information was not found';
    }
    if (message.includes('server') || message.includes('500')) {
      return 'Server issue - we\'re working on it';
    }
    if (message.includes('timeout')) {
      return 'Request timed out - please try again';
    }
    
    return error.message || 'Something went wrong';
  };

  return (
    <div className={`border rounded-lg shadow-lg max-w-sm w-full ${getToastStyles()}`}>
      {/* Progress bar for auto-dismiss */}
      {error.severity === errorManager.SEVERITY.LOW && (
        <div 
          className="absolute bottom-0 left-0 h-1 bg-current opacity-30 transition-all duration-50 ease-linear"
          style={{ width: `${progress}%` }}
        />
      )}

      <div className="p-4">
        <div className="flex items-start">
          <div className="flex-shrink-0 text-lg mr-3">
            {getIcon()}
          </div>
          
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium">
              {getUserFriendlyMessage()}
            </p>
            
            {error.id && (
              <p className="text-xs opacity-75 mt-1 font-mono">
                ID: {error.id.slice(-8)}
              </p>
            )}
          </div>
          
          <button
            onClick={() => {
              setIsVisible(false);
              setTimeout(onDismiss, 300);
            }}
            className="flex-shrink-0 ml-2 text-current opacity-75 hover:opacity-100 transition-opacity"
          >
            ✕
          </button>
        </div>

        {/* Action buttons */}
        <div className="mt-3 flex gap-2">
          {error.recovery === errorManager.RECOVERY.RETRY && onRetry && (
            <button
              onClick={onRetry}
              className="text-xs px-3 py-1 bg-current bg-opacity-20 rounded-md hover:bg-opacity-30 transition-colors"
            >
              Try Again
            </button>
          )}
          
          {onDetails && (
            <button
              onClick={onDetails}
              className="text-xs px-3 py-1 bg-current bg-opacity-20 rounded-md hover:bg-opacity-30 transition-colors"
            >
              Details
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

const ErrorToastContainer = () => {
  const [toasts, setToasts] = useState([]);

  useEffect(() => {
    // Subscribe to error manager
    const unsubscribe = errorManager.subscribe((error) => {
      // Only show certain types of errors as toasts
      if (shouldShowAsToast(error)) {
        addToast(error);
      }
    });

    return unsubscribe;
  }, []);

  const shouldShowAsToast = (error) => {
    // Don't show React errors as toasts (handled by boundary)
    if (error.type === 'react_error') return false;
    
    // Don't show validation errors as toasts (handled inline)
    if (error.category === errorManager.CATEGORIES.VALIDATION) return false;
    
    // Don't show performance errors as toasts (too noisy)
    if (error.category === errorManager.CATEGORIES.PERFORMANCE) return false;
    
    return true;
  };

  const addToast = (error) => {
    const toastId = error.id || Date.now();
    setToasts(prev => [...prev, { ...error, toastId }]);
  };

  const removeToast = (toastId) => {
    setToasts(prev => prev.filter(toast => toast.toastId !== toastId));
  };

  const handleRetry = (error) => {
    if (error.retryCallback) {
      error.retryCallback().catch(() => {
        // Error will be handled by the error manager
      });
    }
    removeToast(error.toastId);
  };

  const handleDetails = (error) => {
    // Show error details modal or console log
    console.group('Error Details');
    console.error('Error:', error);
    console.groupEnd();
    
    // Could open a modal here instead
    alert(`Error Details:\n\nID: ${error.id}\nMessage: ${error.message}\nCategory: ${error.category}\nSeverity: ${error.severity}\n\nCheck console for full details.`);
  };

  return (
    <div className="fixed top-4 right-4 z-50 space-y-2 pointer-events-none">
      {toasts.map((toast) => (
        <div key={toast.toastId} className="pointer-events-auto">
          <Toast
            error={toast}
            onDismiss={() => removeToast(toast.toastId)}
            onRetry={() => handleRetry(toast)}
            onDetails={() => handleDetails(toast)}
          />
        </div>
      ))}
    </div>
  );
};

export default ErrorToastContainer;