import React, { createContext, useContext } from "react";

const ApiKeyContext = createContext(null);

export const ApiKeyProvider = ({ children }) => {
  const value = {
    apiKeys: [],
    addApiKey: () => {},
    deleteApiKey: () => {},
  };

  return (
    <ApiKeyContext.Provider value={value}>{children}</ApiKeyContext.Provider>
  );
};

export const useApiKey = () => {
  const context = useContext(ApiKeyContext);
  if (!context) {
    throw new Error("useApiKey must be used within ApiKeyProvider");
  }
  return context;
};

export default ApiKeyProvider;
