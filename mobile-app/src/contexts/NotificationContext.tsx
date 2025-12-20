import React, { createContext, useContext, ReactNode } from 'react';

interface NotificationContextType {
  showNotification: (message: string, type?: 'info' | 'success' | 'error') => void;
}

const NotificationContext = createContext<NotificationContextType | undefined>(undefined);

interface NotificationProviderProps {
  children: ReactNode;
}

export const NotificationProvider: React.FC<NotificationProviderProps> = ({ children }) => {
  const showNotification = (message: string, type: 'info' | 'success' | 'error' = 'info') => {
    // TODO: Implement notification system
    console.log(`[${type.toUpperCase()}] ${message}`);
  };

  const value = {
    showNotification,
  };

  return <NotificationContext.Provider value={value}>{children}</NotificationContext.Provider>;
};

export const useNotification = () => {
  const context = useContext(NotificationContext);
  if (context === undefined) {
    throw new Error('useNotification must be used within a NotificationProvider');
  }
  return context;
};