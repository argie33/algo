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
              // DON'T separate React and ReactDOM - keep them in main bundle to avoid conflicts
              // Skip React chunking entirely to prevent SECRET_INTERNALS errors
              if (id.includes('react-router')) {
                return 'react-router';
              }
              
              // UI libraries - keep Emotion with MUI for proper initialization order
              if (id.includes('@mui/material') || id.includes('@mui/icons-material') || id.includes('@emotion')) {
                return 'mui';
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
        '@dnd-kit/core',
        '@dnd-kit/sortable',
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
    // Fix React 18 conflicts - prevent duplicates and ensure single instance
    resolve: {
      alias: {
        '@': resolve(__dirname, 'src')
      },
      dedupe: ['react', 'react-dom', 'use-sync-external-store', '@emotion/react', '@emotion/styled']
    }
  }
})
