import React from 'react'

const ResponsiveLayout = ({ children, title, subtitle }) => {
  return (
    <main className="container mx-auto mobile-spacing-normal safe-area-bottom">
      {title && (
        <div className="mb-6">
          <h1 className="mobile-title font-bold text-gray-900 mb-2">{title}</h1>
          {subtitle && (
            <p className="mobile-text text-gray-600">{subtitle}</p>
          )}
        </div>
      )}
      <div className="responsive-content">
        {children}
      </div>
    </main>
  )
}

const ResponsiveCard = ({ children, className = '', title, actions }) => {
  return (
    <div className={`mobile-card ${className}`}>
      {title && (
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-900">{title}</h3>
          {actions && (
            <div className="flex space-x-2">
              {actions}
            </div>
          )}
        </div>
      )}
      {children}
    </div>
  )
}

const ResponsiveGrid = ({ children, columns = { mobile: 1, tablet: 2, desktop: 3 } }) => {
  const gridClasses = [
    'grid gap-4',
    `grid-cols-${columns.mobile}`,
    `md:grid-cols-${columns.tablet}`,
    `lg:grid-cols-${columns.desktop}`
  ].join(' ')

  return (
    <div className={gridClasses}>
      {children}
    </div>
  )
}

const ResponsiveButtonGroup = ({ children, stacked = false }) => {
  const classes = stacked 
    ? 'mobile-button-stack' 
    : 'flex flex-wrap gap-2'

  return (
    <div className={classes}>
      {children}
    </div>
  )
}

const ResponsiveTable = ({ headers, data, renderRow }) => {
  return (
    <div className="table-container">
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-gray-200">
            {headers.map((header, index) => (
              <th
                key={index}
                className="text-left py-3 px-4 font-medium text-gray-900 text-sm"
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, index) => (
            <tr key={index} className="border-b border-gray-100 hover:bg-gray-50">
              {renderRow(row, index)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const ResponsiveModal = ({ isOpen, onClose, title, children }) => {
  if (!isOpen) return null

  return (
    <div className="mobile-modal" onClick={onClose}>
      <div className="mobile-modal-content" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-gray-900">{title}</h2>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700 touch-target"
            aria-label="Close modal"
          >
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

const ResponsiveTabs = ({ tabs, activeTab, onTabChange }) => {
  return (
    <div className="mobile-tabs">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onTabChange(tab.id)}
          className={`mobile-tab ${activeTab === tab.id ? 'active' : ''}`}
        >
          {tab.icon && <span className="mr-2">{tab.icon}</span>}
          {tab.label}
        </button>
      ))}
    </div>
  )
}

const LoadingSpinner = ({ size = 'medium', message }) => {
  const sizeClasses = {
    small: 'w-4 h-4',
    medium: 'w-8 h-8',
    large: 'w-12 h-12'
  }

  return (
    <div className="mobile-loading">
      <div className={`mobile-loading-spinner ${sizeClasses[size]}`} />
      {message && (
        <p className="mt-3 text-sm text-gray-600 text-center">{message}</p>
      )}
    </div>
  )
}

const ResponsiveForm = ({ children, onSubmit, className = '' }) => {
  return (
    <form onSubmit={onSubmit} className={`responsive-form ${className}`}>
      {children}
    </form>
  )
}

const FormGroup = ({ label, error, children, required }) => {
  return (
    <div className="form-group">
      {label && (
        <label className="block text-sm font-medium text-gray-700 mb-1">
          {label}
          {required && <span className="text-red-500 ml-1">*</span>}
        </label>
      )}
      {children}
      {error && (
        <p className="mt-1 text-sm text-red-600">{error}</p>
      )}
    </div>
  )
}

const Input = React.forwardRef(({ className = '', error, ...props }, ref) => {
  return (
    <input
      ref={ref}
      className={`form-input ${error ? 'border-red-300' : ''} ${className}`}
      {...props}
    />
  )
})

const Button = ({ 
  children, 
  variant = 'primary', 
  size = 'medium', 
  fullWidth = false,
  loading = false,
  disabled = false,
  ...props 
}) => {
  const baseClasses = 'font-medium rounded-lg transition-colors touch-target'
  
  const variantClasses = {
    primary: 'bg-blue-500 hover:bg-blue-600 text-white',
    secondary: 'bg-gray-500 hover:bg-gray-600 text-white',
    success: 'bg-green-500 hover:bg-green-600 text-white',
    danger: 'bg-red-500 hover:bg-red-600 text-white',
    outline: 'border border-blue-500 text-blue-500 hover:bg-blue-50'
  }
  
  const sizeClasses = {
    small: 'px-3 py-1.5 text-sm',
    medium: 'px-4 py-2 text-sm',
    large: 'px-6 py-3 text-base'
  }
  
  const classes = [
    baseClasses,
    variantClasses[variant],
    sizeClasses[size],
    fullWidth ? 'w-full' : '',
    disabled || loading ? 'opacity-50 cursor-not-allowed' : ''
  ].filter(Boolean).join(' ')

  return (
    <button
      className={classes}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? (
        <div className="flex items-center justify-center">
          <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin mr-2" />
          Loading...
        </div>
      ) : (
        children
      )}
    </button>
  )
}

export {
  ResponsiveLayout,
  ResponsiveCard,
  ResponsiveGrid,
  ResponsiveButtonGroup,
  ResponsiveTable,
  ResponsiveModal,
  ResponsiveTabs,
  LoadingSpinner,
  ResponsiveForm,
  FormGroup,
  Input,
  Button
}