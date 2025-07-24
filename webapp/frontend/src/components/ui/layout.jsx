import React from 'react';

// Create simple mock components for testing to avoid dependency issues
const TailwindNavigation = ({ children }) => (
  <nav data-testid="tailwind-navigation">{children}</nav>
);

const TailwindHeader = ({ title, user, notifications, onNotificationClick, onProfileClick, showSearch, children }) => (
  <header data-testid="tailwind-header" data-title={title} data-notifications={notifications}>
    {title && <h1>{title}</h1>}
    {user && <span data-testid="user-info">{user.name || user.email}</span>}
    {notifications > 0 && (
      <button 
        data-testid="notification-button" 
        onClick={onNotificationClick}
      >
        {notifications} notifications
      </button>
    )}
    {user && (
      <button 
        data-testid="profile-button" 
        onClick={onProfileClick}
      >
        Profile
      </button>
    )}
    {showSearch && <div data-testid="search-component">Search</div>}
    {children}
  </header>
);

const AppLayout = ({ 
  children,
  headerTitle = "Financial Dashboard",
  user = null,
  notifications = 0,
  onNotificationClick,
  onProfileClick,
  showSearch = true,
  headerChildren
}) => {
  return (
    <div className="h-screen flex overflow-hidden bg-gray-50">
      <TailwindNavigation>
        <div className="flex flex-col flex-1 overflow-hidden">
          <TailwindHeader
            title={headerTitle}
            user={user}
            notifications={notifications}
            onNotificationClick={onNotificationClick}
            onProfileClick={onProfileClick}
            showSearch={showSearch}
          >
            {headerChildren}
          </TailwindHeader>
          
          <main className="flex-1 overflow-y-auto">
            {children}
          </main>
        </div>
      </TailwindNavigation>
    </div>
  );
};

const PageLayout = ({ 
  children,
  title,
  subtitle,
  action,
  breadcrumbs = [],
  className = "max-w-7xl mx-auto py-6 sm:px-6 lg:px-8"
}) => {
  return (
    <div className="min-h-full">
      {(title || subtitle || action || breadcrumbs.length > 0) && (
        <div className="bg-white shadow">
          <div className="px-4 sm:px-6 lg:mx-auto lg:max-w-6xl lg:px-8">
            <div className="py-6 md:flex md:items-center md:justify-between">
              <div className="min-w-0 flex-1">
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
                {title && (
                  <h1 className="text-2xl font-bold leading-tight text-gray-900">
                    {title}
                  </h1>
                )}
                {subtitle && (
                  <p className="mt-1 text-sm text-gray-500">
                    {subtitle}
                  </p>
                )}
              </div>
              {action && (
                <div className="mt-6 flex space-x-3 md:mt-0 md:ml-4">
                  {action}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
      
      <div className={className}>
        {children}
      </div>
    </div>
  );
};

const CardLayout = ({ 
  children, 
  title, 
  subtitle, 
  action,
  className = "",
  padding = "p-6"
}) => {
  return (
    <div className={`bg-white shadow rounded-lg ${className}`}>
      {(title || subtitle || action) && (
        <div className="border-b border-gray-200 px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              {title && (
                <h3 className="text-lg leading-6 font-medium text-gray-900">
                  {title}
                </h3>
              )}
              {subtitle && (
                <p className="mt-1 text-sm text-gray-500">
                  {subtitle}
                </p>
              )}
            </div>
            {action && (
              <div className="flex-shrink-0">
                {action}
              </div>
            )}
          </div>
        </div>
      )}
      <div className={padding}>
        {children}
      </div>
    </div>
  );
};

const GridLayout = ({ 
  children, 
  cols = 1, 
  gap = 6,
  className = ""
}) => {
  const gridCols = {
    1: 'grid-cols-1',
    2: 'grid-cols-1 md:grid-cols-2',
    3: 'grid-cols-1 md:grid-cols-2 lg:grid-cols-3',
    4: 'grid-cols-1 md:grid-cols-2 lg:grid-cols-4',
    6: 'grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6'
  };

  const gapClass = `gap-${gap}`;

  return (
    <div className={`grid ${gridCols[cols]} ${gapClass} ${className}`}>
      {children}
    </div>
  );
};

const FlexLayout = ({ 
  children, 
  direction = 'row', 
  align = 'start', 
  justify = 'start',
  gap = 4,
  wrap = false,
  className = ""
}) => {
  const flexDirection = direction === 'col' ? 'flex-col' : 'flex-row';
  const alignItems = `items-${align}`;
  const justifyContent = `justify-${justify}`;
  const gapClass = `gap-${gap}`;
  const flexWrap = wrap ? 'flex-wrap' : '';

  return (
    <div className={`flex ${flexDirection} ${alignItems} ${justifyContent} ${gapClass} ${flexWrap} ${className}`}>
      {children}
    </div>
  );
};

export { AppLayout, PageLayout, CardLayout, GridLayout, FlexLayout };