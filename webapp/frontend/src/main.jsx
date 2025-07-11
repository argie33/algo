import React from 'react'
import ReactDOM from 'react-dom/client'

console.log('🚀 main.jsx loaded - MINIMAL REACT APP - v1.1.0');

// Minimal dashboard component without any dependencies that might fail
const MinimalDashboard = () => {
  const [stockData, setStockData] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);

  React.useEffect(() => {
    // Fetch stock data from API
    const fetchData = async () => {
      try {
        const apiUrl = window.__CONFIG__?.API_URL || 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev';
        console.log('📡 Fetching data from:', apiUrl);
        
        const response = await fetch(`${apiUrl}/stocks`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const data = await response.json();
        console.log('✅ Data fetched:', data.length, 'stocks');
        
        setStockData(data.slice(0, 20)); // Show first 20 stocks
        setLoading(false);
      } catch (err) {
        console.error('❌ API Error:', err);
        setError(err.message);
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  const containerStyle = {
    padding: '20px',
    fontFamily: 'Inter, Arial, sans-serif',
    backgroundColor: '#f5f5f5',
    minHeight: '100vh'
  };

  const headerStyle = {
    background: 'linear-gradient(135deg, #1976d2 0%, #42a5f5 100%)',
    color: 'white',
    padding: '20px',
    borderRadius: '12px',
    marginBottom: '20px',
    textAlign: 'center'
  };

  const cardStyle = {
    background: 'white',
    padding: '15px',
    borderRadius: '8px',
    boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
    marginBottom: '10px',
    display: 'grid',
    gridTemplateColumns: '1fr 100px 100px 100px',
    gap: '15px',
    alignItems: 'center'
  };

  const priceStyle = (change) => ({
    fontWeight: 'bold',
    color: change >= 0 ? '#2e7d32' : '#d32f2f'
  });

  if (loading) {
    return (
      <div style={containerStyle}>
        <div style={headerStyle}>
          <h1>Financial Dashboard</h1>
          <p>Loading market data...</p>
        </div>
        <div style={{textAlign: 'center', padding: '50px'}}>
          <div style={{
            display: 'inline-block',
            width: '40px',
            height: '40px',
            border: '4px solid #f3f3f3',
            borderTop: '4px solid #1976d2',
            borderRadius: '50%',
            animation: 'spin 1s linear infinite'
          }}></div>
          <style>{`
            @keyframes spin {
              0% { transform: rotate(0deg); }
              100% { transform: rotate(360deg); }
            }
          `}</style>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={containerStyle}>
        <div style={{...headerStyle, background: 'linear-gradient(135deg, #d32f2f 0%, #f44336 100%)'}}>
          <h1>Financial Dashboard</h1>
          <p>Error loading data: {error}</p>
        </div>
        <div style={{textAlign: 'center', padding: '20px'}}>
          <button 
            onClick={() => window.location.reload()}
            style={{
              padding: '10px 20px',
              backgroundColor: '#1976d2',
              color: 'white',
              border: 'none',
              borderRadius: '5px',
              cursor: 'pointer'
            }}
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={containerStyle}>
      <div style={headerStyle}>
        <h1>Financial Dashboard</h1>
        <p>Real-time stock market data • {stockData.length} stocks loaded</p>
      </div>
      
      <div style={{marginBottom: '20px'}}>
        <h2 style={{color: '#333', marginBottom: '15px'}}>Top Stocks</h2>
        <div style={{
          ...cardStyle,
          backgroundColor: '#1976d2',
          color: 'white',
          fontWeight: 'bold'
        }}>
          <div>Symbol</div>
          <div>Price</div>
          <div>Change</div>
          <div>Volume</div>
        </div>
        
        {stockData.map((stock, index) => (
          <div key={index} style={cardStyle}>
            <div>
              <strong>{stock.symbol || stock.ticker}</strong>
              <div style={{fontSize: '12px', color: '#666', marginTop: '2px'}}>
                {stock.name || stock.company_name || 'N/A'}
              </div>
            </div>
            <div style={priceStyle(stock.change || stock.price_change || 0)}>
              ${(stock.price || stock.current_price || 0).toFixed(2)}
            </div>
            <div style={priceStyle(stock.change || stock.price_change || 0)}>
              {stock.change || stock.price_change || 0 >= 0 ? '+' : ''}
              {(stock.change || stock.price_change || 0).toFixed(2)}
            </div>
            <div style={{fontSize: '12px', color: '#666'}}>
              {(stock.volume || 0).toLocaleString()}
            </div>
          </div>
        ))}
      </div>
      
      <div style={{textAlign: 'center', padding: '20px', color: '#666'}}>
        <p>✅ Dashboard loaded successfully • API connection working</p>
        <p>Last updated: {new Date().toLocaleTimeString()}</p>
      </div>
    </div>
  );
};

// Render the minimal dashboard
try {
  console.log('🔧 Creating React root...');
  const root = ReactDOM.createRoot(document.getElementById('root'));
  
  console.log('🔧 Rendering minimal dashboard...');
  root.render(<MinimalDashboard />);
  
  console.log('✅ Minimal dashboard rendered successfully!');
} catch (error) {
  console.error('❌ Error rendering minimal dashboard:', error);
  // Fallback to plain HTML
  document.getElementById('root').innerHTML = `
    <div style="padding: 20px; text-align: center; font-family: Arial, sans-serif;">
      <h1 style="color: #d32f2f;">Dashboard Loading Failed</h1>
      <p><strong>Error:</strong> ${error.message}</p>
      <p>Please check browser console for details.</p>
      <button onclick="window.location.reload()" style="padding: 10px 20px; background: #1976d2; color: white; border: none; border-radius: 5px; cursor: pointer;">
        Reload Page
      </button>
    </div>
  `;
}
