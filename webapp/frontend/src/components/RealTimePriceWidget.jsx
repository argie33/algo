import React, { useState, useEffect, useRef } from "react";
import {
  Box,
  Typography,
  Chip,
  LinearProgress,
  Skeleton,
  Alert,
} from "@mui/material";
import {
  TrendingUp,
  TrendingDown,
  TrendingFlat,
  Warning,
} from "@mui/icons-material";
import { formatCurrency, formatPercentage } from "../utils/formatters";
import dataCache from "../services/dataCache";

const RealTimePriceWidget = ({
  symbol,
  showChart = false,
  compact = false,
}) => {
  const [priceData, setPriceData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isStale, setIsStale] = useState(false);
  const updateIntervalRef = useRef(null);

  // Simulate price movements for development
  const simulatePriceMovement = (basePrice) => {
    const volatility = 0.002; // 0.2% volatility
    const trend = Math.random() > 0.5 ? 1 : -1;
    const change = basePrice * volatility * trend * Math.random();
    return basePrice + change;
  };

  const fetchPriceData = async () => {
    try {
      const data = await dataCache.get(
        `/api/stocks/quote/${symbol}`,
        {},
        {
          cacheType: "marketData",
          fetchFunction: async () => {
            try {
              const response = await fetch(`/api/stocks/quote/${symbol}`);
              if (!response.ok) throw new Error("Failed to fetch price");
              const result = await response.json();

              // If we get real data, use it
              if (result && result.price) {
                return result;
              }

              // ⚠️ MOCK DATA FALLBACK - Replace with real API when available
              const basePrice = Math.random() * 200 + 50;
              const previousClose =
                basePrice * (1 - (Math.random() * 0.04 - 0.02));
              const dayChange = basePrice - previousClose;
              const dayChangePercent = (dayChange / previousClose) * 100;

              return {
                symbol,
                price: basePrice,
                previousClose,
                dayChange,
                dayChangePercent,
                volume: Math.floor(Math.random() * 50000000),
                marketCap: basePrice * Math.floor(Math.random() * 1000000000),
                dayHigh: basePrice * 1.02,
                dayLow: basePrice * 0.98,
                lastUpdate: new Date().toISOString(),
                isMockData: true, // Flag to indicate this is mock data
              };
            } catch (error) {
              console.error("Price fetch error:", error);
              // ⚠️ ERROR FALLBACK - Return mock data on error
              const basePrice = 150 + Math.random() * 50;
              return {
                symbol,
                price: basePrice,
                previousClose: basePrice * 0.98,
                dayChange: basePrice * 0.02,
                dayChangePercent: 2.0,
                volume: 25000000,
                lastUpdate: new Date().toISOString(),
                isMockData: true, // Flag to indicate this is mock data
              };
            }
          },
        }
      );

      setPriceData(data);
      setIsStale(false);
      setLoading(false);
    } catch (error) {
      console.error("Failed to fetch price data:", error);
      setLoading(false);
      setIsStale(true);
    }
  };

  useEffect(() => {
    // Initial fetch
    fetchPriceData();

    // Set up update interval - much less frequent to avoid costs
    const updateInterval = 3600000; // 1 hour refresh

    updateIntervalRef.current = setInterval(() => {
      fetchPriceData();
    }, updateInterval);

    return () => {
      if (updateIntervalRef.current) {
        clearInterval(updateIntervalRef.current);
      }
    };
  }, [symbol]);

  if (loading) {
    return (
      <Box>
        <Skeleton variant="text" width={100} height={30} />
        <Skeleton variant="text" width={150} height={24} />
      </Box>
    );
  }

  if (!priceData) {
    return (
      <Typography variant="body2" color="text.secondary">
        No data available
      </Typography>
    );
  }

  const isPositive = priceData.dayChange >= 0;
  const changeColor = isPositive ? "success.main" : "error.main";
  const TrendIcon = isPositive
    ? TrendingUp
    : priceData.dayChange === 0
      ? TrendingFlat
      : TrendingDown;

  if (compact) {
    return (
      <Box display="flex" alignItems="center" gap={1}>
        <Typography variant="h6" fontWeight="bold">
          {formatCurrency(priceData.price)}
        </Typography>
        <Chip
          size="small"
          icon={<TrendIcon />}
          label={`${isPositive ? "+" : ""}${formatPercentage(priceData.dayChangePercent)}`}
          sx={{
            backgroundColor: isPositive ? "success.light" : "error.light",
            color: changeColor,
            fontWeight: "bold",
          }}
        />
      </Box>
    );
  }

  return (
    <Box>
      {priceData.isMockData && (
        <Alert severity="warning" sx={{ mb: 1, py: 0.5 }}>
          <Typography variant="caption">
            ⚠️ MOCK DATA - Connect to real API for production
          </Typography>
        </Alert>
      )}
      <Box display="flex" alignItems="baseline" gap={2} mb={1}>
        <Typography variant="h4" fontWeight="bold" color="text.primary">
          {formatCurrency(priceData.price)}
        </Typography>
        <Box display="flex" alignItems="center" gap={0.5}>
          <TrendIcon sx={{ color: changeColor, fontSize: 20 }} />
          <Typography variant="h6" color={changeColor} fontWeight="medium">
            {isPositive && "+"}
            {formatCurrency(Math.abs(priceData.dayChange))}
          </Typography>
          <Typography variant="h6" color={changeColor} fontWeight="medium">
            ({isPositive && "+"}
            {formatPercentage(priceData.dayChangePercent)})
          </Typography>
        </Box>
      </Box>

      {!compact && (
        <>
          <Box display="flex" gap={3} mb={2}>
            <Box>
              <Typography variant="caption" color="text.secondary">
                Volume
              </Typography>
              <Typography variant="body2" fontWeight="medium">
                {(priceData.volume / 1000000).toFixed(2)}M
              </Typography>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">
                Day Range
              </Typography>
              <Typography variant="body2" fontWeight="medium">
                {formatCurrency(priceData.dayLow)} -{" "}
                {formatCurrency(priceData.dayHigh)}
              </Typography>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">
                Prev Close
              </Typography>
              <Typography variant="body2" fontWeight="medium">
                {formatCurrency(priceData.previousClose)}
              </Typography>
            </Box>
          </Box>

          {dataCache.isMarketHours() && (
            <Box>
              <LinearProgress
                variant="indeterminate"
                sx={{
                  height: 2,
                  backgroundColor: "grey.200",
                  "& .MuiLinearProgress-bar": {
                    backgroundColor: changeColor,
                  },
                }}
              />
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ mt: 0.5, display: "block" }}
              >
                Live - Market Open • Last update:{" "}
                {new Date(priceData.lastUpdate).toLocaleTimeString()}
              </Typography>
            </Box>
          )}

          {!dataCache.isMarketHours() && (
            <Typography variant="caption" color="text.secondary">
              After Hours • Last update:{" "}
              {new Date(priceData.lastUpdate).toLocaleTimeString()}
            </Typography>
          )}

          {isStale && (
            <Typography variant="caption" color="warning.main">
              ⚠️ Data may be delayed
            </Typography>
          )}
        </>
      )}
    </Box>
  );
};

export default RealTimePriceWidget;
