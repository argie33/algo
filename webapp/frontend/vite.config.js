import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

// https://vitejs.dev/config/ - Clean implementation
export default defineConfig(({ mode }) => {
  const isDevelopment = mode === 'development'
  const isProduction = mode === 'production'
  
  // API URL configuration - use AWS API Gateway for all environments
  const apiUrl = process.env.VITE_API_URL || 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev'
  
  console.log('Vite Config:', {
    mode,
    isDevelopment,
    isProduction,
    apiUrl,
    viteApiUrl: process.env.VITE_API_URL
  })

  return {
    plugins: [react()],
    
    // Test configuration
    test: {
      environment: 'jsdom',
      setupFiles: ['src/tests/setup.js'],
      globals: true,
      css: false, // Disable CSS processing in tests for better performance
      environmentOptions: {
        jsdom: {
          resources: 'usable',
        },
      },
      // Add React-specific test configuration
      pool: 'forks',
      poolOptions: {
        forks: {
          singleFork: true,
        },
      },
    },
    
    build: {
      target: 'es2020',
      sourcemap: mode !== 'production',
      rollupOptions: {
        output: {
          // Simple, effective chunking
          manualChunks: {
            'react-vendor': ['react', 'react-dom'],
            'mui': ['@mui/material', '@mui/icons-material'],
            'query': ['@tanstack/react-query'],
            'charts': ['recharts', 'chart.js'],
            'utils': ['lodash', 'date-fns', 'axios']
          }
        }
      }
    },
    
    server: {
      port: 3000,
      proxy: isDevelopment ? {
        '/api': {
          target: apiUrl,
          changeOrigin: true,
          timeout: 45000, // Longer timeout for Lambda cold starts in development
          configure: (proxy, options) => {
            console.log('Proxy configured for:', options.target)
          }
        }
      } : undefined
    },
    
    define: {
      // Expose environment variables to the client
      __APP_VERSION__: JSON.stringify(process.env.npm_package_version),
      __BUILD_TIME__: JSON.stringify(new Date().toISOString()),
      __MODE__: JSON.stringify(mode),
      __IS_DEV__: JSON.stringify(isDevelopment),
      __IS_PROD__: JSON.stringify(isProduction),
    },
    
    resolve: {
      alias: {
        '@': resolve(__dirname, 'src')
        // No forced React aliasing - let Node resolution work
      }
    },
    
    // Simplified optimization
    optimizeDeps: {
      include: ['react', 'react-dom', '@tanstack/react-query']
    }
  }
})