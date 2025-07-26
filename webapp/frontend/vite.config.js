import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'
import { reactPreloadPlugin } from './src/utils/reactPreloadPlugin.js'

// https://vitejs.dev/config/ - updated to trigger workflow
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
    plugins: [react(), reactPreloadPlugin()],
    
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
      outDir: 'dist',
      sourcemap: isProduction ? false : true,
      minify: 'esbuild',
      target: 'es2015',
      chunkSizeWarningLimit: 1000, // Increased limit for better performance
      rollupOptions: {
        output: {
          // Add proper globals for React
          globals: {
            'react': 'React',
            'react-dom': 'ReactDOM'
          },
          // OPTIMIZED CHUNK SPLITTING for massive bundle size reduction
          manualChunks(id) {
            // Create more granular chunks for node_modules
            if (id.includes('node_modules')) {
              // Core React (keep together for stability)
              if (id.includes('react') && !id.includes('react-router')) {
                return 'vendor-react';
              }
              
              // React Router (separate for route-level lazy loading)
              if (id.includes('react-router')) {
                return 'react-router';
              }
              
              // MUI Core - Split into smaller chunks
              if (id.includes('@mui/material')) {
                return 'mui-material';
              }
              if (id.includes('@mui/icons-material')) {
                return 'mui-icons';
              }
              if (id.includes('@emotion')) {
                return 'mui-emotion';
              }
              
              // Charts & Visualization (lazy loaded)
              if (id.includes('recharts') || id.includes('d3')) {
                return 'charts';
              }
              
              // AWS Services (lazy loaded)
              if (id.includes('aws-amplify') || id.includes('@aws-amplify') || id.includes('@aws-sdk')) {
                return 'aws';
              }
              
              // Data management libraries
              if (id.includes('@tanstack/react-query') || id.includes('swr')) {
                return 'data-management';
              }
              
              // Utility libraries (lazy loaded)
              if (id.includes('lodash') || id.includes('ramda')) {
                return 'lodash';
              }
              if (id.includes('date-fns') || id.includes('moment') || id.includes('dayjs')) {
                return 'date-utils';
              }
              if (id.includes('numeral') || id.includes('accounting')) {
                return 'number-utils';
              }
              
              // Animation libraries (lazy loaded)
              if (id.includes('framer-motion') || id.includes('react-spring')) {
                return 'animations';
              }
              
              // HTTP libraries
              if (id.includes('axios') || id.includes('fetch')) {
                return 'http';
              }
              
              // Form libraries (lazy loaded)
              if (id.includes('formik') || id.includes('react-hook-form')) {
                return 'forms';
              }
              
              // Everything else - much smaller now
              return 'vendor';
            }
            
            // Split application code by logical groupings
            if (id.includes('/pages/')) {
              const page = id.split('/pages/')[1].split('/')[0].split('.')[0];
              // Group related pages together
              if (['Portfolio', 'PortfolioPerformance', 'PortfolioOptimization', 'TradeHistory'].includes(page)) {
                return 'page-portfolio';
              }
              if (['Options', 'OptionsAnalytics', 'OptionsStrategies', 'OptionsFlow', 'VolatilitySurface', 'GreeksMonitor'].some(name => page.includes(name))) {
                return 'page-options';
              }
              if (['Crypto', 'CryptoMarketOverview', 'CryptoPortfolio', 'CryptoRealTimeTracker', 'CryptoAdvancedAnalytics'].some(name => page.includes(name))) {
                return 'page-crypto';
              }
              if (['Sentiment', 'SocialMediaSentiment', 'NewsSentiment'].some(name => page.includes(name))) {
                return 'page-sentiment';
              }
              if (['HFT', 'Neural', 'LiveData'].some(name => page.includes(name))) {
                return 'page-trading';
              }
              return `page-${page}`;
            }
            
            // Component splitting
            if (id.includes('/components/')) {
              if (id.includes('Chart') || id.includes('Graph')) {
                return 'chart-components';
              }
              if (id.includes('auth') || id.includes('Auth')) {
                return 'auth-components';
              }
              return 'components';
            }
            
            // Service and utility splitting
            if (id.includes('/services/')) {
              return 'services';
            }
            if (id.includes('/utils/')) {
              return 'app-utils';
            }
          },
          // Optimize chunk naming
          chunkFileNames: (chunkInfo) => {
            const facadeModuleId = chunkInfo.facadeModuleId ? chunkInfo.facadeModuleId.split('/').pop().replace('.jsx', '').replace('.js', '') : 'chunk';
            return `assets/${facadeModuleId}-[hash].js`;
          }
        },
        // Performance optimizations
        maxParallelFileOps: 5,
        cache: false // Disable cache for consistent builds
      },
      // Optimize asset handling
      assetsInlineLimit: 4096, // Inline smaller assets
      cssCodeSplit: true // Split CSS for better caching
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
        define: {
          // Ensure React is available globally for all modules
          'global': 'globalThis',
          'process.env.NODE_ENV': '"production"'
        }
      },
    },
    // Fix React 18 conflicts - prevent duplicates and ensure single instance
    resolve: {
      alias: {
        '@': resolve(__dirname, 'src'),
        // Force React to resolve to single instance
        'react': resolve(__dirname, 'node_modules/react'),
        'react-dom': resolve(__dirname, 'node_modules/react-dom')
      },
      dedupe: ['react', 'react-dom', 'use-sync-external-store', '@emotion/react', '@emotion/styled', 'recharts']
    }
  }
})
