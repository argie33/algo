// MINIMAL VERSION - Test if MUI createPalette error is eliminated
import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

// Core TailwindCSS styling only
import './index.css'

// Simple minimal app
const MinimalApp = () => {
  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-blue-600 text-white shadow-md">
        <div className="container mx-auto px-4">
          <div className="flex items-center justify-between h-16">
            <h1 className="text-xl font-bold">Financial Trading Platform</h1>
          </div>
        </div>
      </nav>
      <main className="container mx-auto px-4 py-8">
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
          <h2 className="text-2xl font-bold text-gray-900 mb-4">
            ✅ MUI-Free Application
          </h2>
          <p className="text-gray-700 mb-4">
            This version eliminates all MUI dependencies to prevent createPalette.js errors.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
              <h3 className="font-semibold text-green-800">✅ No MUI Dependencies</h3>
              <p className="text-green-700 text-sm">Zero Material-UI imports</p>
            </div>
            <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
              <h3 className="font-semibold text-blue-800">🎨 TailwindCSS Only</h3>
              <p className="text-blue-700 text-sm">Pure utility-first styling</p>
            </div>
          </div>
          <div className="mt-6">
            <button className="bg-blue-500 hover:bg-blue-600 text-white font-medium py-2 px-4 rounded-lg transition-colors">
              Test Button
            </button>
          </div>
        </div>
      </main>
    </div>
  )
}

console.log('🚀 Minimal Financial Platform initializing...')
console.log('📍 Location:', window.location.href)
console.log('🎯 Root element:', !!document.getElementById('root'))

try {
  const root = ReactDOM.createRoot(document.getElementById('root'))
  root.render(
    <BrowserRouter>
      <MinimalApp />
    </BrowserRouter>
  )
  console.log('✅ Minimal application rendered successfully!')
} catch (error) {
  console.error('❌ Error rendering minimal application:', error)
  
  // Fallback to basic HTML
  document.getElementById('root').innerHTML = `
    <div style="padding: 20px; text-align: center; font-family: Arial, sans-serif;">
      <h1 style="color: #d32f2f;">Minimal Application Failed</h1>
      <p><strong>Error:</strong> ${error.message}</p>
      <p>Check browser console for details.</p>
    </div>
  `
}