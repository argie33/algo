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
  const apiUrl = env.VITE_API_URL || (isDevelopment ? "http://localhost:3000" : "");

  console.log("Vite Config:", {
    mode,
    isDevelopment,
    isProduction,
    apiUrl,
    viteApiUrl: env.VITE_API_URL,
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
          // Don't externalize any dependencies - bundle everything for compatibility
          return false;
        },
        output: {
          manualChunks: {
            vendor: ['react', 'react-dom'],
            mui: ['@mui/material', '@mui/icons-material'],
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
        // Fix AWS Amplify ES module imports completely
        "aws-amplify": resolve(__dirname, "src/aws-amplify-mock"),
        "aws-amplify/auth": resolve(__dirname, "src/aws-amplify-mock/auth"),
        "aws-amplify/auth/cognito": resolve(__dirname, "src/aws-amplify-mock/auth/cognito"),
        "@aws-amplify/auth": resolve(__dirname, "src/aws-amplify-mock/auth"),
        "@aws-amplify/core": resolve(__dirname, "src/aws-amplify-mock/core"),
        "@aws-amplify/auth/cognito": resolve(__dirname, "src/aws-amplify-mock/auth/cognito"),
        "@aws-amplify/auth/lib-esm/providers/cognito": resolve(__dirname, "src/aws-amplify-mock/auth/cognito"),
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
      exclude: ["@aws-amplify/auth", "aws-amplify"],
      esbuildOptions: {
        loader: {
          ".js": "jsx",
        },
      },
      force: true, // Force pre-bundling to respect overrides
    },
  };
});
