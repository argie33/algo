import React, { useState, useEffect } from "react";
import { Box, Typography, CircularProgress, Alert } from "@mui/material";

const DeepValueStocks = () => {
  const [stocks, setStocks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchDeepValueStocks();
  }, []);

  const fetchDeepValueStocks = async () => {
    try {
      setLoading(true);
      setError(null);

      const response = await fetch("/api/stocks/deep-value?limit=100");

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      const result = await response.json();
      const stocksData = result.data || result;

      if (Array.isArray(stocksData)) {
        setStocks(stocksData);
      } else {
        throw new Error("Invalid response format");
      }
    } catch (err) {
      console.error("Error fetching deep value stocks:", err);
      setError(err.message || "Failed to load deep value stocks");
      setStocks([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box sx={{ padding: 3 }}>
      <Typography variant="h4" gutterBottom>
        💎 Deep Value Stock Picks
      </Typography>

      <Typography variant="body1" paragraph>
        Discover undervalued stocks with strong fundamental value but lower composite scores.
      </Typography>

      {loading && <CircularProgress />}
      {error && <Alert severity="error">{error}</Alert>}

      {!loading && !error && stocks.length === 0 && (
        <Alert severity="info">No stocks found</Alert>
      )}

      {!loading && !error && stocks.length > 0 && (
        <Box>
          <Typography variant="h6">Found {stocks.length} deep value stocks</Typography>
          <pre>{JSON.stringify(stocks.slice(0, 3), null, 2)}</pre>
        </Box>
      )}
    </Box>
  );
};

export default DeepValueStocks;
