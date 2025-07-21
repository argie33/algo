import React from 'react';
import { BellIcon, UserCircleIcon, MagnifyingGlassIcon } from '@heroicons/react/24/outline';

const TailwindHeader = ({ 
  title = "Financial Dashboard", 
  user = null,
  notifications = 0,
  onNotificationClick,
  onProfileClick,
  showSearch = true,
  children 
}) => {
  return (
    <header className="bg-white shadow-sm border-b border-gray-200">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 justify-between items-center">
          {/* Left side - Title */}
          <div className="flex items-center">
            <h1 className="text-xl font-semibold text-gray-900">{title}</h1>
          </div>

          {/* Center - Search (optional) */}
          {showSearch && (
            <div className="flex-1 max-w-lg mx-8">
              <div className="relative">
                <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
                  <MagnifyingGlassIcon className="h-5 w-5 text-gray-400" aria-hidden="true" />
                </div>
                <input
                  type="search"
                  placeholder="Search stocks, symbols..."
                  className="block w-full rounded-md border-0 py-1.5 pl-10 pr-3 text-gray-900 ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-blue-600 sm:text-sm sm:leading-6"
                />
              </div>
            </div>
          )}

          {/* Right side - Actions */}
          <div className="flex items-center gap-x-4">
            {/* Custom children (API status, etc) */}
            {children}

            {/* Notifications */}
            <button
              type="button"
              className="relative rounded-full bg-white p-1 text-gray-400 hover:text-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
              onClick={onNotificationClick}
            >
              <span className="sr-only">View notifications</span>
              <BellIcon className="h-6 w-6" aria-hidden="true" />
              {notifications > 0 && (
                <span className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-xs text-white">
                  {notifications > 9 ? '9+' : notifications}
                </span>
              )}
            </button>

            {/* Profile */}
            <button
              type="button"
              className="flex items-center gap-x-2 rounded-full bg-white p-1 text-gray-400 hover:text-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
              onClick={onProfileClick}
            >
              <span className="sr-only">Open user menu</span>
              <UserCircleIcon className="h-8 w-8" aria-hidden="true" />
              {user && (
                <span className="hidden sm:block text-sm font-medium text-gray-700">
                  {user.name || user.email}
                </span>
              )}
            </button>
          </div>
        </div>
      </div>
    </header>
  );
};

const PageHeader = ({ 
  title, 
  subtitle, 
  action, 
  breadcrumbs = [],
  className = "" 
}) => {
  return (
    <div className={`bg-white px-4 py-5 border-b border-gray-200 sm:px-6 ${className}`}>
      {/* Breadcrumbs */}
      {breadcrumbs.length > 0 && (
        <nav className="flex mb-2" aria-label="Breadcrumb">
          <ol className="flex items-center space-x-2">
            {breadcrumbs.map((crumb, index) => (
              <li key={index}>
                <div className="flex items-center">
                  {index > 0 && (
                    <svg className="mr-2 h-4 w-4 text-gray-300" fill="currentColor" viewBox="0 0 20 20">
                      <path d="M5.555 17.776l8-16 .894.448-8 16-.894-.448z" />
                    </svg>
                  )}
                  {crumb.href ? (
                    <a
                      href={crumb.href}
                      className="text-sm font-medium text-gray-500 hover:text-gray-700"
                    >
                      {crumb.name}
                    </a>
                  ) : (
                    <span className="text-sm font-medium text-gray-900">{crumb.name}</span>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </nav>
      )}

      {/* Header content */}
      <div className="flex items-center justify-between">
        <div className="min-w-0 flex-1">
          <h2 className="text-2xl font-bold leading-7 text-gray-900 sm:truncate sm:text-3xl sm:tracking-tight">
            {title}
          </h2>
          {subtitle && (
            <p className="mt-1 text-sm text-gray-500">{subtitle}</p>
          )}
        </div>
        {action && (
          <div className="flex-shrink-0">
            {action}
          </div>
        )}
      </div>
    </div>
  );
};

export default TailwindHeader;
export { PageHeader };