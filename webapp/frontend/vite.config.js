import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

// https://vitejs.dev/config/
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
      chunkSizeWarningLimit: 1000,
      rollupOptions: {
        output: {
          manualChunks: {
            vendor: ['react', 'react-dom', 'react-router-dom'],
            mui: ['@mui/material', '@mui/icons-material', '@mui/lab', '@mui/x-data-grid', '@mui/x-date-pickers'],
            charts: ['recharts', 'chart.js', 'react-chartjs-2'],
            aws: ['aws-amplify', '@aws-amplify/auth', '@aws-amplify/core', '@aws-amplify/ui-react'],
            utils: ['axios', 'lodash', 'numeral', 'date-fns'],
            codemirror: ['@codemirror/lang-javascript', '@codemirror/lang-python', '@uiw/react-codemirror'],
            'react-query': ['@tanstack/react-query'],
            emotion: ['@emotion/react', '@emotion/styled'],
            animations: ['framer-motion'],
            dnd: ['react-beautiful-dnd']
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
      // Reduce the number of files opened during optimization
      esbuildOptions: {
        loader: {
          '.js': 'jsx',
        },
      },
    }
  }
})
