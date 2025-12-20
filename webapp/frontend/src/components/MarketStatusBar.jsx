import React, { useState, useEffect } from "react";
import { Box, Typography, Chip, Paper, Divider } from "@mui/material";
import { Circle, TrendingUp, TrendingDown } from "@mui/icons-material";
import dataCache from "../services/dataCache";
import { formatPercentage, formatNumber } from "../utils/formatters";

const MarketStatusBar = () => {
  const [marketStatus, setMarketStatus] = useState({
    isOpen: false,
    session: "Closed",
    nextChange: null,
    indices: [],
  });

  const [loading, setLoading] = useState(true);

  const fetchMarketStatus = async () => {
    try {
      const data = await dataCache.get(
        "/api/market/status",
        {},
        {
          cacheType: "marketData",
          fetchFunction: async () => {
            // Check current time for market status
            const now = new Date();
            const day = now.getDay();
            const hour = now.getHours();
            const minute = now.getMinutes();
            const currentTime = hour + minute / 60;

            const isWeekday = day > 0 && day < 6;
            const isMarketHours = currentTime >= 9.5 && currentTime < 16;
            const isPreMarket = currentTime >= 4 && currentTime < 9.5;
            const isAfterHours = currentTime >= 16 && currentTime < 20;

            let session = "Closed";
            let nextChange = null;

            if (isWeekday) {
              if (isMarketHours) {
                session = "Open";
                nextChange = `Closes at 4:00 PM`;
              } else if (isPreMarket) {
                session = "Pre-Market";
                nextChange = `Opens at 9:30 AM`;
              } else if (isAfterHours) {
                session = "After-Hours";
                nextChange = `Closes at 8:00 PM`;
              }
            }

            // Simulate index data
            const indices = [
              {
                symbol: "SPX",
                name: "S&P 500",
                value: 4500 + (Math.random() - 0.5) * 100,
                change: (Math.random() - 0.5) * 2,
                changePercent: (Math.random() - 0.5) * 2,
              },
              {
                symbol: "DJI",
                name: "Dow Jones",
                value: 35000 + (Math.random() - 0.5) * 500,
                change: (Math.random() - 0.5) * 200,
                changePercent: (Math.random() - 0.5) * 2,
              },
              {
                symbol: "IXIC",
                name: "Nasdaq",
                value: 14000 + (Math.random() - 0.5) * 300,
                change: (Math.random() - 0.5) * 100,
                changePercent: (Math.random() - 0.5) * 3,
              },
            ];

            return {
              isOpen: session === "Open",
              session,
              nextChange,
              indices,
            };
          },
        }
      );

      setMarketStatus(data);
      setLoading(false);
    } catch (error) {
      if (import.meta.env && import.meta.env.DEV)
        console.error("Failed to fetch market status:", error);
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMarketStatus();

    // Update every hour
    const interval = setInterval(fetchMarketStatus, 3600000);

    return () => clearInterval(interval);
  }, []);

  if (loading || !marketStatus) {
    return null;
  }

  const getSessionColor = () => {
    if (!marketStatus?.session) {
      return "default";
    }
    switch (marketStatus.session) {
      case "Open":
        return "success";
      case "Pre-Market":
        return "warning";
      case "After-Hours":
        return "info";
      default:
        return "error";
    }
  };

  return (
    <Paper
      elevation={0}
      data-testid="market-status-bar"
      sx={{
        p: 1.5,
        backgroundColor: "background.default",
        borderBottom: "1px solid",
        borderColor: "divider",
      }}
    >
      <Box
        display="flex"
        alignItems="center"
        justifyContent="space-between"
        flexWrap="wrap"
        gap={2}
      >
        {/* Market Status */}
        <Box display="flex" alignItems="center" gap={2}>
          <Chip
            icon={<Circle sx={{ fontSize: 12 }} />}
            label={`Market Status: ${marketStatus?.session || "Unknown"}`}
            color={getSessionColor()}
            size="small"
            sx={{ fontWeight: "bold" }}
          />
          {marketStatus?.nextChange && (
            <Typography variant="caption" color="text.secondary">
              {marketStatus.nextChange}
            </Typography>
          )}
        </Box>

        {/* Market Indices */}
        <Box display="flex" alignItems="center" gap={3}>
          {marketStatus?.indices &&
            (marketStatus.indices || []).map((index, i) => (
              <React.Fragment key={index.symbol}>
                {i > 0 && <Divider orientation="vertical" flexItem />}
                <Box display="flex" alignItems="center" gap={1}>
                  <Box>
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{ fontWeight: 500 }}
                    >
                      {index.name}
                    </Typography>
                    <Box display="flex" alignItems="center" gap={0.5}>
                      <Typography variant="body2" fontWeight="bold">
                        {formatNumber(index.value, 0)}
                      </Typography>
                      {index.change >= 0 ? (
                        <TrendingUp
                          sx={{ fontSize: 16, color: "success.main" }}
                        />
                      ) : (
                        <TrendingDown
                          sx={{ fontSize: 16, color: "error.main" }}
                        />
                      )}
                      <Typography
                        variant="body2"
                        color={
                          index.change >= 0 ? "success.main" : "error.main"
                        }
                        fontWeight="medium"
                      >
                        {formatPercentage(index.changePercent)}
                      </Typography>
                    </Box>
                  </Box>
                </Box>
              </React.Fragment>
            ))}
        </Box>

        {/* Cache Stats (Development Only) */}
        {process.env.NODE_ENV === "development" && (
          <Box>
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ cursor: "pointer" }}
              onClick={() =>
                import.meta.env &&
                import.meta.env.DEV &&
                console.log("Cache Stats:", dataCache.getStats())
              }
            >
              Cache: {dataCache.cache.size} items
            </Typography>
          </Box>
        )}
      </Box>
    </Paper>
  );
};

export default MarketStatusBar;
