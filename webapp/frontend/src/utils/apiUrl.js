// Get the base API URL for fetch requests
export const getApiUrl = () => {
  // 1. Runtime injection (AWS deployment)
  if (typeof window !== "undefined" && window.__CONFIG__?.API_URL) {
    return window.__CONFIG__.API_URL;
  }

  // 2. Build-time env var
  if (import.meta.env?.VITE_API_URL) {
    return import.meta.env.VITE_API_URL;
  }

  // 3. Dev: relative path, Vite proxy handles it
  return "/";
};
