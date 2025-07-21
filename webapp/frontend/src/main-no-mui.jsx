// COMPLETE NO-MUI VERSION - Zero MUI dependencies to eliminate createPalette errors
// Initialize essential utilities FIRST
import './utils/muiPrevention.js'
import './utils/browserCompatibility.js'
import './utils/seoOptimization.js'
import './utils/mobileOptimization.js'
import './utils/offlineSupport.js'
import asyncErrorHandler from './utils/asyncErrorHandler.js'
import memoryLeakPrevention from './utils/memoryLeakPrevention.js'
import performanceMonitor from './utils/performanceMonitor.js'

import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '../hooks/useSimpleFetch.js'
import { BrowserRouter } from 'react-router-dom'

// Core TailwindCSS styling only
import './index.css'

// Use TailwindCSS error boundary instead of MUI
import ErrorBoundary from './components/ErrorBoundaryTailwind'
import { LoadingProvider } from './components/LoadingStateManager'

// Import App without MUI dependencies
import AppNoMUI from './AppNoMUI'

// Enhanced initialization logging
console.log('🚀 Financial Platform (No MUI) initializing...')
console.log('📍 Location:', window.location.href)
console.log('📄 Document state:', document.readyState)
console.log('🎯 Root element:', !!document.getElementById('root'))

// Log system capabilities
import { getCompatibilityReport } from './utils/browserCompatibility.js'
import { getSystemHealth } from './utils/asyncErrorHandler.js'
import { getSecurityStatus } from './utils/securityUtils.js'
import { getAccessibilityAudit } from './utils/accessibilityUtils.js'
import { runSEOAudit } from './utils/seoOptimization.js'
import { getMobileOptimizationStatus } from './utils/mobileOptimization.js'
import { getOfflineStatus } from './utils/offlineSupport.js'

console.group('🔍 System Status')
console.log('Browser compatibility:', getCompatibilityReport())
console.log('Error handling health:', getSystemHealth())
console.log('Security status:', getSecurityStatus())
console.log('Accessibility audit:', getAccessibilityAudit())
console.log('SEO audit:', runSEOAudit())
console.log('Mobile optimization:', getMobileOptimizationStatus())
console.log('Offline support:', getOfflineStatus())
console.groupEnd()

// Create a client
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

// Simple app wrapper without any MUI dependencies
const AppWithProviders = () => {
  return (
    <LoadingProvider>
      <AppNoMUI />
    </LoadingProvider>
  )
}

try {
  console.log('🔧 Creating React root...')
  const root = ReactDOM.createRoot(document.getElementById('root'))
  
  console.log('🔧 Rendering MUI-free application...')
  root.render(
    <ErrorBoundary>
      <BrowserRouter>
        <QueryClientProvider client={queryClient}>
          <AppWithProviders />
        </QueryClientProvider>
      </BrowserRouter>
    </ErrorBoundary>
  )
  
  console.log('✅ Application rendered successfully without MUI!')
} catch (error) {
  console.error('❌ Error rendering application:', error)
  
  // Fallback to basic dashboard
  document.getElementById('root').innerHTML = `
    <div style="padding: 20px; text-align: center; font-family: Arial, sans-serif;">
      <h1 style="color: #d32f2f;">Application Loading Failed</h1>
      <p><strong>Error:</strong> ${error.message}</p>
      <p>Check browser console for details.</p>
      <button onclick="window.location.reload()" style="padding: 10px 20px; background: #1976d2; color: white; border: none; border-radius: 5px; cursor: pointer;">
        Reload Page
      </button>
    </div>
  `
}