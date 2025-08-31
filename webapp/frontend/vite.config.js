import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const isDevelopment = mode === "development";
  const isProduction = mode === "production";

  // API URL configuration
  const apiUrl =
    process.env.VITE_API_URL || (isDevelopment ? "http://localhost:3001" : "");

  console.log("Vite Config:", {
    mode,
    isDevelopment,
    isProduction,
    apiUrl,
    viteApiUrl: process.env.VITE_API_URL,
  });

  return {
    plugins: [
      react({
        jsxRuntime: 'automatic'
      })
    ],
    build: {
      outDir: "dist",
      sourcemap: true,
      chunkSizeWarningLimit: 1000,
      rollupOptions: {
        external: (id) => {
          // Force react-is to use the specific version we want
          if (id === 'react-is' || id.includes('react-is/')) {
            return false; // Bundle it but with our override
          }
          return false;
        },
        output: {
          manualChunks: (id) => {
            // Core React libraries
            if (
              id.includes("node_modules/react") ||
              id.includes("node_modules/react-dom")
            ) {
              return "vendor";
            }
            // MUI components and icons
            if (id.includes("node_modules/@mui")) {
              return "mui";
            }
            // Chart libraries
            if (id.includes("node_modules/recharts")) {
              return "charts";
            }
            // Router libraries
            if (id.includes("node_modules/react-router")) {
              return "router";
            }
            // React Query
            if (id.includes("node_modules/@tanstack/react-query")) {
              return "query";
            }
            // Core pages
            if (
              id.includes("src/pages/Portfolio.jsx") ||
              id.includes("src/pages/Dashboard.jsx") ||
              id.includes("src/pages/Settings.jsx")
            ) {
              return "pages";
            }
            // Trading related pages
            if (
              id.includes("src/pages/Trading") ||
              id.includes("src/pages/AdvancedScreener") ||
              id.includes("src/pages/Backtest")
            ) {
              return "trading";
            }
            // Analysis pages
            if (
              id.includes("src/pages/Technical") ||
              id.includes("src/pages/News") ||
              id.includes("src/pages/Sentiment")
            ) {
              return "analysis";
            }
            // Other large node_modules
            if (id.includes("node_modules")) {
              return "vendor-misc";
            }
          },
        },
        // Limit concurrent operations to prevent EMFILE
        maxParallelFileOps: 5,
      },
    },
    server: {
      port: 3000,
      proxy: isDevelopment
        ? {
            "/api": {
              target: apiUrl,
              changeOrigin: true,
              timeout: 45000, // Longer timeout for Lambda cold starts in development
              configure: (proxy, options) => {
                console.log("Proxy configured for:", options.target);
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
      // Ensure React production mode
      "process.env.NODE_ENV": JSON.stringify(
        isProduction ? "production" : "development"
      ),
      // Fix React Context compatibility issue
      global: 'globalThis',
    },
    resolve: {
      alias: {
        "@": resolve(__dirname, "src"),
        // Force specific react-is version to avoid compatibility issues
        "react-is": resolve(__dirname, "node_modules/react-is"),
      },
    },
    optimizeDeps: {
      esbuildOptions: {
        loader: {
          ".js": "jsx",
        },
      },
      force: true, // Force pre-bundling to respect overrides
    },
  };
});
