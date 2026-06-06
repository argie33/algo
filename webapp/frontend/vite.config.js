import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // Load env file based on `mode` in the current working directory.
  const env = loadEnv(mode, process.cwd(), '');

  const isDevelopment = mode === "development";
  const isProduction = mode === "production";

  // API URL configuration - use loadEnv to properly read .env file
  // In development: leave VITE_API_URL empty so api.js uses relative paths
  // The Vite proxy will handle routing /api/* to localhost:3001
  // In production: use explicit URL from VITE_API_URL environment variable
  const apiUrl = env.VITE_API_URL || ""; // Empty for dev, explicit for prod
  // Vite proxy target for development (backend running on localhost:3001)
  const proxyTarget = isDevelopment ? "http://localhost:3001" : "";

  return {
    plugins: [
      react({
        jsxRuntime: 'automatic'
      })
    ],
    build: {
      outDir: "dist",
      sourcemap: isDevelopment,
      chunkSizeWarningLimit: 500,
      rollupOptions: {
        external: (id) => {
          // Don't externalize any dependencies - bundle everything for compatibility
          return false;
        },
        output: {
          manualChunks: {
            vendor: ['react', 'react-dom'],
            // @mui/icons-material intentionally excluded from manualChunks so
            // Rollup can tree-shake unused icons (~400 icons → only imported ones)
            mui: ['@mui/material'],
            charts: ['recharts'],
            utils: ['axios', 'date-fns', 'numeral']
          },
        },
        // Limit concurrent operations to prevent EMFILE
        maxParallelFileOps: 5,
      },
    },
    server: {
      port: 5173,
      strictPort: false,
      proxy: isDevelopment
        ? {
            "/api": {
              target: proxyTarget,
              changeOrigin: true,
              timeout: 35000, // 35s to match Lambda's 30s statement timeout + 5s buffer for network/serialization
              configure: (proxy, options) => {
              },
            },
          }
        : undefined,
    },
    define: {
      // Expose environment variables to the client
      __APP_VERSION__: JSON.stringify(process.env.npm_package_version),
      __BUILD_TIME__: JSON.stringify(new Date().toISOString()),
      __MODE__: JSON.stringify(mode),
      __IS_DEV__: JSON.stringify(isDevelopment),
      __IS_PROD__: JSON.stringify(isProduction),
      // Ensure React production mode and fix React Context compatibility
      "process.env.NODE_ENV": JSON.stringify(
        isProduction ? "production" : "development"
      ),
      global: 'globalThis',
    },
    resolve: {
      alias: {
        "@": resolve(__dirname, "src"),
        // Force MUI styled-engine to use the emotion version
        "@mui/styled-engine": resolve(__dirname, "node_modules/@mui/styled-engine"),
        // AWS Amplify is now used directly from node_modules (v6.17.0)
        // Removed mock aliases to enable proper authentication
      },
    },
    optimizeDeps: {
      include: [
        "@mui/styled-engine",
        "@mui/material",
        "@mui/icons-material",
        "@emotion/react",
        "@emotion/styled",
        "react-is",
        "prop-types",
        "hoist-non-react-statics"
      ],
      exclude: ["@aws-amplify/auth", "aws-amplify", "lucide-react"],
      esbuildOptions: {
        loader: {
          ".js": "jsx",
        },
      },
      force: true, // Force pre-bundling to respect overrides
    },
  };
});
