// COMPLETELY MUI-FREE VERSION - No createPalette.js errors
import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// Core basic CSS styling only (no TailwindCSS issues)
import './index-basic.css'
import './mobile-responsive.css'

// Essential utilities (carefully selected)
import './utils/muiPrevention.js'
import './utils/browserCompatibility.js'
import performanceMonitor from './utils/performanceMonitor.js'

// Import the completely MUI-free App component
import App from './App.jsx'

// Simple error boundary
const ErrorBoundary = ({ children }) => {
  const [hasError, setHasError] = React.useState(false)
  
  React.useEffect(() => {
    const handleError = (error) => {
      console.error('React Error:', error)
      setHasError(true)
    }
    
    window.addEventListener('error', handleError)
    window.addEventListener('unhandledrejection', handleError)
    
    return () => {
      window.removeEventListener('error', handleError)
      window.removeEventListener('unhandledrejection', handleError)
    }
  }, [])
  
  if (hasError) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="bg-white p-6 rounded-lg border border-gray-200">
          <h2 className="text-2xl font-bold text-gray-900 mb-4">Something went wrong</h2>
          <p className="text-gray-700 mb-4">Please reload the page to try again.</p>
          <button 
            onClick={() => window.location.reload()}
            className="bg-blue-500 hover:bg-blue-600 text-white font-medium py-2 px-4 rounded-lg transition-colors"
          >
            Reload Page
          </button>
        </div>
      </div>
    )
  }
  
  return children
}


// Create QueryClient
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 3,
      staleTime: 30000,
      cacheTime: 10 * 60 * 1000,
      refetchOnWindowFocus: false,
    },
  },
})

console.log('🚀 MUI-Free Financial Platform initializing...')
console.log('📍 Location:', window.location.href)
console.log('🎯 Root element:', !!document.getElementById('root'))
console.log('✅ All MUI dependencies removed - no createPalette.js errors!')

try {
  const root = ReactDOM.createRoot(document.getElementById('root'))
  root.render(
    <ErrorBoundary>
      <BrowserRouter>
        <QueryClientProvider client={queryClient}>
          <App />
        </QueryClientProvider>
      </BrowserRouter>
    </ErrorBoundary>
  )
  console.log('✅ MUI-Free application rendered successfully!')
} catch (error) {
  console.error('❌ Error rendering MUI-Free application:', error)
  
  // Fallback to basic HTML
  document.getElementById('root').innerHTML = `
    <div style="padding: 20px; text-align: center; font-family: Arial, sans-serif;">
      <h1 style="color: #d32f2f;">Integrated Application Failed</h1>
      <p><strong>Error:</strong> ${error.message}</p>
      <p>Check browser console for details.</p>
      <button onclick="window.location.reload()" style="padding: 10px 20px; background: #1976d2; color: white; border: none; border-radius: 5px; cursor: pointer;">
        Reload Page
      </button>
    </div>
  `
}