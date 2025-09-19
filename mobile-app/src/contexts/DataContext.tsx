import React, { createContext, useContext, useState, ReactNode } from 'react';

interface DataContextType {
  portfolioData: any;
  marketData: any;
  refreshData: () => void;
}

const DataContext = createContext<DataContextType | undefined>(undefined);

interface DataProviderProps {
  children: ReactNode;
}

export const DataProvider: React.FC<DataProviderProps> = ({ children }) => {
  const [portfolioData, setPortfolioData] = useState(null);
  const [marketData, setMarketData] = useState(null);

  const refreshData = () => {
    // TODO: Implement data refresh
    console.log('Refreshing data...');
  };

  const value = {
    portfolioData,
    marketData,
    refreshData,
  };

  return <DataContext.Provider value={value}>{children}</DataContext.Provider>;
};

export const useData = () => {
  const context = useContext(DataContext);
  if (context === undefined) {
    throw new Error('useData must be used within a DataProvider');
  }
  return context;
};