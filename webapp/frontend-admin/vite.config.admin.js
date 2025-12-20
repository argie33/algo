import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

// Vite config for Admin/Portfolio site (private, auth required)
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const isDevelopment = mode === "development";
  const isProduction = mode === "production";

  // API URL for admin site - should point to shared backend
  const apiUrl = env.VITE_API_URL || (isDevelopment ? "http://localhost:3001" : "");

  console.log("Vite Config (Admin Site):", {
    mode,
    isDevelopment,
    isProduction,
    apiUrl,
    siteName: "Admin Portal - Portfolio & Tools",
  });

  return {
    plugins: [
      react({
        jsxRuntime: 'automatic'
      })
    ],
    build: {
      outDir: "dist-admin",
      sourcemap: true,
      chunkSizeWarningLimit: 1000,
      rollupOptions: {
        external: (id) => false,
        output: {
          manualChunks: {
            vendor: ['react', 'react-dom'],
            mui: ['@mui/material', '@mui/icons-material'],
            charts: ['recharts'],
            utils: ['axios', 'date-fns', 'numeral']
          },
        },
        maxParallelFileOps: 5,
      },
    },
    server: {
      port: 5174,
      proxy: isDevelopment
        ? {
            "/api": {
              target: apiUrl,
              changeOrigin: true,
              timeout: 45000,
              configure: (proxy, options) => {
                console.log("Admin site proxy configured for:", options.target);
              },
            },
          }
        : undefined,
    },
    define: {
      __APP_VERSION__: JSON.stringify(process.env.npm_package_version),
      __BUILD_TIME__: JSON.stringify(new Date().toISOString()),
      __MODE__: JSON.stringify(mode),
      __IS_DEV__: JSON.stringify(isDevelopment),
      __IS_PROD__: JSON.stringify(isProduction),
      __SITE_NAME__: JSON.stringify("Admin Portal"),
      __SITE_TYPE__: JSON.stringify("private"),
      "process.env.NODE_ENV": JSON.stringify(
        isProduction ? "production" : "development"
      ),
      global: 'globalThis',
    },
    resolve: {
      alias: {
        "@": resolve(__dirname, "src"),
        "@mui/styled-engine": resolve(__dirname, "node_modules/@mui/styled-engine"),
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
      force: true,
    },
  };
});
