# Paper Trading UI Toggle Design

## 🎛️ **Frontend Toggle Implementation**

### **Toggle Component Design**

```jsx
// PaperTradingToggle.jsx
import React, { useState, useContext } from 'react';
import { Switch, FormControlLabel, Chip } from '@mui/material';
import { TradingContext } from '../context/TradingContext';

const PaperTradingToggle = () => {
  const { accountType, setAccountType } = useContext(TradingContext);
  
  const handleToggle = (event) => {
    const newAccountType = event.target.checked ? 'live' : 'paper';
    setAccountType(newAccountType);
  };

  return (
    <div className="trading-mode-toggle">
      <FormControlLabel
        control={
          <Switch
            checked={accountType === 'live'}
            onChange={handleToggle}
            color="warning"
            size="medium"
          />
        }
        label={
          <div className="toggle-label">
            <Chip 
              label={accountType === 'paper' ? 'Paper Trading' : 'Live Trading'}
              color={accountType === 'paper' ? 'success' : 'error'}
              variant="filled"
              size="small"
            />
          </div>
        }
      />
    </div>
  );
};

export default PaperTradingToggle;
```

### **Context Provider for Trading Mode**

```jsx
// context/TradingContext.jsx
import React, { createContext, useState, useEffect } from 'react';

export const TradingContext = createContext();

export const TradingProvider = ({ children }) => {
  const [accountType, setAccountType] = useState('paper'); // Default to paper
  
  // Persist trading mode preference
  useEffect(() => {
    const savedMode = localStorage.getItem('tradingMode');
    if (savedMode && ['paper', 'live'].includes(savedMode)) {
      setAccountType(savedMode);
    }
  }, []);
  
  useEffect(() => {
    localStorage.setItem('tradingMode', accountType);
  }, [accountType]);
  
  return (
    <TradingContext.Provider value={{ accountType, setAccountType }}>
      {children}
    </TradingContext.Provider>
  );
};
```

### **API Integration Hook**

```jsx
// hooks/useApiWithAccountType.js
import { useContext } from 'react';
import { TradingContext } from '../context/TradingContext';

export const useApiWithAccountType = () => {
  const { accountType } = useContext(TradingContext);
  
  const makeApiCall = async (endpoint, options = {}) => {
    const url = new URL(endpoint, window.location.origin);
    url.searchParams.append('accountType', accountType);
    
    const response = await fetch(url.toString(), options);
    return response.json();
  };
  
  return { makeApiCall, accountType };
};
```

## 📱 **Integration Examples**

### **Dashboard Component**

```jsx
// Dashboard.jsx
import React, { useEffect, useState } from 'react';
import { useApiWithAccountType } from '../hooks/useApiWithAccountType';
import PaperTradingToggle from '../components/PaperTradingToggle';

const Dashboard = () => {
  const { makeApiCall, accountType } = useApiWithAccountType();
  const [performanceData, setPerformanceData] = useState(null);
  const [riskData, setRiskData] = useState(null);
  
  useEffect(() => {
    loadDashboardData();
  }, [accountType]); // Reload when account type changes
  
  const loadDashboardData = async () => {
    try {
      const [performance, risk] = await Promise.all([
        makeApiCall('/api/performance/dashboard'),
        makeApiCall('/api/risk/dashboard')
      ]);
      
      setPerformanceData(performance);
      setRiskData(risk);
    } catch (error) {
      console.error('Failed to load dashboard data:', error);
    }
  };
  
  return (
    <div className="dashboard">
      <div className="dashboard-header">
        <h1>Portfolio Dashboard</h1>
        <PaperTradingToggle />
      </div>
      
      <div className="trading-mode-indicator">
        {accountType === 'paper' ? (
          <div className="paper-mode-alert">
            📝 You are in Paper Trading mode - No real money at risk
          </div>
        ) : (
          <div className="live-mode-alert">
            💰 You are in Live Trading mode - Real money transactions
          </div>
        )}
      </div>
      
      {/* Dashboard content that updates based on account type */}
    </div>
  );
};
```

### **Portfolio Component**

```jsx
// Portfolio.jsx
import React, { useEffect, useState } from 'react';
import { useApiWithAccountType } from '../hooks/useApiWithAccountType';

const Portfolio = () => {
  const { makeApiCall, accountType } = useApiWithAccountType();
  const [portfolio, setPortfolio] = useState(null);
  
  useEffect(() => {
    loadPortfolio();
  }, [accountType]);
  
  const loadPortfolio = async () => {
    const data = await makeApiCall('/api/portfolio/holdings');
    setPortfolio(data);
  };
  
  return (
    <div className="portfolio">
      <h2>Portfolio Holdings ({accountType === 'paper' ? 'Paper' : 'Live'})</h2>
      {/* Portfolio content */}
    </div>
  );
};</function>
```

## 🎨 **UI/UX Design Guidelines**

### **Visual Indicators**

```css
/* Paper Trading Mode */
.paper-mode {
  border-left: 4px solid #4caf50;
  background-color: #e8f5e8;
}

.paper-mode-alert {
  background: linear-gradient(135deg, #4caf50, #45a049);
  color: white;
  padding: 8px 16px;
  border-radius: 4px;
  margin-bottom: 16px;
}

/* Live Trading Mode */
.live-mode {
  border-left: 4px solid #f44336;
  background-color: #fde8e8;
}

.live-mode-alert {
  background: linear-gradient(135deg, #f44336, #d32f2f);
  color: white;
  padding: 8px 16px;
  border-radius: 4px;
  margin-bottom: 16px;
}

/* Toggle Component */
.trading-mode-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
}
```

### **Confirmation Dialog for Live Mode**

```jsx
// ConfirmLiveTradingDialog.jsx
import React from 'react';
import { Dialog, DialogTitle, DialogContent, DialogActions, Button, Typography } from '@mui/material';

const ConfirmLiveTradingDialog = ({ open, onConfirm, onCancel }) => {
  return (
    <Dialog open={open} onClose={onCancel}>
      <DialogTitle>⚠️ Switch to Live Trading?</DialogTitle>
      <DialogContent>
        <Typography>
          You are about to switch to Live Trading mode where real money will be at risk.
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
          • All trades will use real money
          • Portfolio values will reflect actual holdings
          • Risk calculations will be based on live positions
        </Typography>
      </DialogContent>
      <DialogActions>
        <Button onClick={onCancel}>Cancel</Button>
        <Button onClick={onConfirm} color="error" variant="contained">
          Switch to Live Trading
        </Button>
      </DialogActions>
    </Dialog>
  );
};
```

## 🔄 **Backend Integration Points**

### **API Endpoints Support** ✅

All these endpoints now support the `?accountType=paper|live` parameter:

- `/api/portfolio/holdings?accountType=paper`
- `/api/performance/dashboard?accountType=live`
- `/api/risk/dashboard?accountType=paper`
- `/api/performance/portfolio/:id?accountType=live`
- `/api/risk/var?accountType=paper`

### **Response Format** ✅

```json
{
  "success": true,
  "data": { /* endpoint data */ },
  "accountType": "paper",
  "tradingMode": "Paper Trading",
  "timestamp": "2025-07-25T...",
  "paperTradingInfo": {
    "isPaperAccount": true,
    "virtualCash": 100000,
    "restrictions": ["No real money risk"],
    "benefits": ["Risk-free testing"]
  }
}
```

## 📋 **Implementation Checklist**

### **Frontend Tasks**
- [ ] Create `PaperTradingToggle` component
- [ ] Implement `TradingContext` for state management
- [ ] Add `useApiWithAccountType` hook
- [ ] Update all API calls to include `accountType` parameter
- [ ] Add visual indicators for trading mode
- [ ] Implement confirmation dialog for live mode switch
- [ ] Add trading mode persistence (localStorage)

### **Integration Points** ✅
- [x] Backend API endpoints support `accountType` parameter
- [x] Response format includes trading mode information
- [x] Error handling for account type validation
- [x] Paper trading metadata in responses

The toggle allows users to seamlessly switch between paper and live trading modes, with all data (portfolio, performance, risk) automatically updating to reflect the selected mode.