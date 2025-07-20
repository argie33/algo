import React from 'react';
import { ExclamationTriangleIcon, ChartBarIcon } from '@heroicons/react/24/outline';

export function DataNotAvailable({ 
  message = "Data not available", 
  suggestion = "Please try again later or check your connection.",
  showIcon = true,
  type = "default" // "default", "chart", "table", "api"
}) {
  const icons = {
    default: ExclamationTriangleIcon,
    chart: ChartBarIcon,
    table: ExclamationTriangleIcon,
    api: ExclamationTriangleIcon
  };

  const Icon = icons[type] || ExclamationTriangleIcon;

  return (
    <div className="flex flex-col items-center justify-center p-8 text-center bg-gray-50 rounded-lg border border-gray-200">
      {showIcon && (
        <Icon className="h-12 w-12 text-gray-400 mb-4" />
      )}
      <h3 className="text-lg font-medium text-gray-900 mb-2">
        {message}
      </h3>
      <p className="text-sm text-gray-500 max-w-sm">
        {suggestion}
      </p>
    </div>
  );
}

export function LoadingFallback({ message = "Loading..." }) {
  return (
    <div className="flex flex-col items-center justify-center p-8 text-center">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mb-4"></div>
      <p className="text-sm text-gray-500">{message}</p>
    </div>
  );
}

export function ErrorFallback({ 
  error, 
  resetErrorBoundary,
  message = "Something went wrong" 
}) {
  return (
    <div className="flex flex-col items-center justify-center p-8 text-center bg-red-50 rounded-lg border border-red-200">
      <ExclamationTriangleIcon className="h-12 w-12 text-red-400 mb-4" />
      <h3 className="text-lg font-medium text-red-900 mb-2">
        {message}
      </h3>
      {error && (
        <p className="text-sm text-red-700 mb-4 max-w-sm">
          {error.message}
        </p>
      )}
      {resetErrorBoundary && (
        <button
          onClick={resetErrorBoundary}
          className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-red-600 hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500"
        >
          Try again
        </button>
      )}
    </div>
  );
}

export default DataNotAvailable;