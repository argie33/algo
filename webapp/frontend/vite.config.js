import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

// https://vitejs.dev/config/ - updated to trigger workflow
export default defineConfig(({ mode }) => {
  const isDevelopment = mode === 'development'
  const isProduction = mode === 'production'
  
  // API URL configuration
  const apiUrl = process.env.VITE_API_URL || (isDevelopment ? 'http://localhost:3001' : 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev')
  
  console.log('Vite Config:', {
    mode,
    isDevelopment,
    isProduction,
    apiUrl,
    viteApiUrl: process.env.VITE_API_URL
  })

  return {
    plugins: [react()],
    build: {
      outDir: 'dist',
      sourcemap: true,
      chunkSizeWarningLimit: 500,
      rollupOptions: {
        output: {
          manualChunks(id) {
            // Split into smaller, more specific chunks for better caching
            if (id.includes('node_modules')) {
              // Core React libraries
              if (id.includes('react') && !id.includes('react-dom') && !id.includes('react-router')) {
                return 'react';
              }
              if (id.includes('react-dom')) {
                return 'react-dom';
              }
              if (id.includes('react-router')) {
                return 'react-router';
              }
              
              // UI libraries
              if (id.includes('@mui/material') || id.includes('@mui/icons-material')) {
                return 'mui';
              }
              if (id.includes('@emotion')) {
                return 'emotion';
              }
              
              // Chart libraries
              if (id.includes('recharts')) {
                return 'charts';
              }
              
              // AWS services
              if (id.includes('aws-amplify') || id.includes('@aws-amplify')) {
                return 'aws';
              }
              
              // Data management
              if (id.includes('@tanstack/react-query')) {
                return 'react-query';
              }
              
              // Utility libraries  
              if (id.includes('lodash')) {
                return 'lodash';
              }
              if (id.includes('date-fns') || id.includes('numeral')) {
                return 'date-utils';
              }
              if (id.includes('framer-motion')) {
                return 'animations';
              }
              if (id.includes('axios')) {
                return 'http';
              }
              
              // Everything else goes to vendor (smaller now)
              return 'vendor';
            }
            
            // Split our own code by feature for better lazy loading
            if (id.includes('/pages/')) {
              const page = id.split('/pages/')[1].split('/')[0].split('.')[0];
              return `page-${page}`;
            }
            if (id.includes('/components/') && id.includes('Chart')) {
              return 'chart-components';
            }
            if (id.includes('/components/')) {
              return 'components';
            }
            if (id.includes('/services/')) {
              return 'services';
            }
            if (id.includes('/utils/')) {
              return 'app-utils';
            }
          }
        },
        // Limit concurrent operations to prevent EMFILE
        maxParallelFileOps: 5
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
    optimizeDeps: {
      include: [
        'recharts',
        'framer-motion',
        'react-beautiful-dnd',
        'react',
        'react-dom',
        'react/jsx-runtime'
      ],
      force: true,
      // Reduce the number of files opened during optimization
      esbuildOptions: {
        loader: {
          '.js': 'jsx',
        },
      },
    },
    // Fix React 18 useState conflicts - use built-in useSyncExternalStore
    resolve: {
      alias: {
        '@': resolve(__dirname, 'src'),
        // Force React to be resolved from node_modules to prevent duplicates
        'react': resolve(__dirname, 'node_modules/react'),
        'react-dom': resolve(__dirname, 'node_modules/react-dom'),
        // use-sync-external-store now properly overridden in node_modules
      },
      dedupe: ['react', 'react-dom', 'use-sync-external-store']
    }
  }
})
