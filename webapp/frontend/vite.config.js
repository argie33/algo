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
    resolve: {
      alias: {
        '@': resolve(__dirname, 'src'),
        'use-sync-external-store/shim/index.js': resolve(__dirname, 'node_modules/use-sync-external-store/shim/index.js'),
      }
    },
    build: {
      outDir: 'dist',
      sourcemap: true,
      chunkSizeWarningLimit: 500,
      rollupOptions: {
        output: {
          manualChunks(id) {
            // Split into smaller, more specific chunks
            if (id.includes('node_modules')) {
              if (id.includes('react') || id.includes('react-dom') || id.includes('react-router')) {
                return 'react-core';
              }
              if (id.includes('@mui/material')) {
                return 'mui-core';
              }
              if (id.includes('@mui/icons-material')) {
                return 'mui-icons';
              }
              if (id.includes('recharts')) {
                return 'charts';
              }
              if (id.includes('aws-amplify') || id.includes('@aws-amplify')) {
                return 'aws';
              }
              if (id.includes('@tanstack/react-query')) {
                return 'react-query';
              }
              if (id.includes('lodash') || id.includes('date-fns') || id.includes('numeral')) {
                return 'utils';
              }
              // Everything else goes to vendor
              return 'vendor';
            }
            
            // Split our own code by page/feature
            if (id.includes('/pages/')) {
              const page = id.split('/pages/')[1].split('/')[0].split('.')[0];
              return `page-${page}`;
            }
            if (id.includes('/components/')) {
              return 'components';
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
        '@uiw/react-codemirror',
        '@codemirror/lang-javascript',
        '@codemirror/lang-python'
      ],
      force: true,
      // Reduce the number of files opened during optimization
      esbuildOptions: {
        loader: {
          '.js': 'jsx',
        },
      },
    }
  }
})
