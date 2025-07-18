import React, { useState, useEffect } from 'react'

const ResponsiveNavigation = ({ currentRoute, navigate }) => {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)
  const [isMobile, setIsMobile] = useState(false)

  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 768)
    }
    
    checkMobile()
    window.addEventListener('resize', checkMobile)
    
    return () => window.removeEventListener('resize', checkMobile)
  }, [])

  const handleNavigate = (path) => {
    navigate(path)
    setIsMobileMenuOpen(false)
  }

  const menuItems = [
    { path: '/', label: 'Dashboard', icon: '📊' },
    { path: '/portfolio', label: 'Portfolio', icon: '💼' },
    { path: '/live-data', label: 'Live Data', icon: '📈' },
    { path: '/settings', label: 'Settings', icon: '⚙️' }
  ]

  return (
    <>
      <nav className="bg-blue-600 text-white shadow-md safe-area-top">
        <div className="container mx-auto">
          <div className="flex items-center justify-between h-16">
            {/* Logo/Brand */}
            <div className="flex items-center">
              <h1 className="text-xl font-bold">
                {isMobile ? 'FinDash' : 'Financial Trading Platform'}
              </h1>
            </div>

            {/* Desktop Navigation */}
            <div className="desktop-nav items-center space-x-4">
              {menuItems.map((item) => (
                <button
                  key={item.path}
                  onClick={() => handleNavigate(item.path)}
                  className={`px-3 py-2 rounded-md text-sm font-medium transition-colors touch-target ${
                    currentRoute === item.path 
                      ? 'bg-blue-700' 
                      : 'hover:bg-blue-700'
                  }`}
                >
                  <span className="hidden-mobile">{item.icon} </span>
                  {item.label}
                </button>
              ))}
            </div>

            {/* Mobile Menu Button */}
            <div className="mobile-nav">
              <button
                onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
                className="touch-target"
                aria-label="Toggle menu"
              >
                <div className={`hamburger ${isMobileMenuOpen ? 'active' : ''}`}>
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
              </button>
            </div>
          </div>
        </div>
      </nav>

      {/* Mobile Menu Overlay */}
      <div
        className={`mobile-menu-overlay ${isMobileMenuOpen ? 'active' : ''}`}
        onClick={() => setIsMobileMenuOpen(false)}
      />

      {/* Mobile Menu */}
      <div className={`mobile-menu ${isMobileMenuOpen ? 'active' : ''}`}>
        <div className="mobile-menu-header">
          <h2 className="text-lg font-semibold text-gray-900">Menu</h2>
          <button
            onClick={() => setIsMobileMenuOpen(false)}
            className="text-gray-500 hover:text-gray-700"
            aria-label="Close menu"
          >
            ✕
          </button>
        </div>
        
        <div className="space-y-2">
          {menuItems.map((item) => (
            <button
              key={item.path}
              onClick={() => handleNavigate(item.path)}
              className={`mobile-menu-item w-full text-left ${
                currentRoute === item.path ? 'text-blue-600 bg-blue-50' : ''
              }`}
            >
              <span className="mr-3">{item.icon}</span>
              {item.label}
            </button>
          ))}
        </div>
        
        <div className="mt-8 pt-4 border-t border-gray-200">
          <div className="text-sm text-gray-500">
            Financial Dashboard v1.0.6
          </div>
        </div>
      </div>
    </>
  )
}

export default ResponsiveNavigation