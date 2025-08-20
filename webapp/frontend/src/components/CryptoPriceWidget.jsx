import React, { useState } from "react";
import {
  Card,
  CardContent,
  Typography,
  Box,
  Chip,
  IconButton,
  Menu,
  MenuItem,
  CircularProgress,
  Alert,
} from "@mui/material";
import {
  TrendingUp,
  TrendingDown,
  MoreVert,
  Refresh,
  Star,
  StarBorder,
  ShowChart,
} from "@mui/icons-material";
import { useQuery } from "@tanstack/react-query";
import apiService from "../utils/apiService.jsx";

function CryptoPriceWidget({
  symbol,
  compact = false,
  showChart = false,
  onAddToWatchlist,
  onRemoveFromWatchlist,
  isInWatchlist = false,
}) {
  const [anchorEl, setAnchorEl] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);

  console.log(`💰 [CRYPTO-WIDGET] Rendering price widget for ${symbol}`);

  const {
    data: priceData,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ["cryptoPrice", symbol, refreshKey],
    queryFn: () =>
      apiService.get(`/crypto/prices/${symbol}?vs_currency=usd&timeframe=24h`),
    refetchInterval: 30000, // Refresh every 30 seconds
    staleTime: 25000,
    cacheTime: 60000,
    enabled: !!symbol,
  });

  const handleMenuOpen = (event) => {
    setAnchorEl(event.currentTarget);
  };

  const handleMenuClose = () => {
    setAnchorEl(null);
  };

  const handleRefresh = () => {
    console.log(`🔄 [CRYPTO-WIDGET] Manual refresh for ${symbol}`);
    setRefreshKey((prev) => prev + 1);
    refetch();
    handleMenuClose();
  };

  const handleWatchlistToggle = () => {
    if (isInWatchlist) {
      onRemoveFromWatchlist?.(symbol);
    } else {
      onAddToWatchlist?.(symbol);
    }
    handleMenuClose();
  };

  const formatCurrency = (value, decimals = 2) => {
    if (!value && value !== 0) return "N/A";

    if (value >= 1000) {
      return `$${Number(value).toLocaleString("en-US", {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      })}`;
    } else {
      return `$${Number(value).toFixed(decimals)}`;
    }
  };

  const formatPercentage = (value, showSign = true) => {
    if (!value && value !== 0) return "N/A";
    const formatted = `${Math.abs(value).toFixed(2)}%`;
    if (!showSign) return formatted;
    return value >= 0 ? `+${formatted}` : `-${formatted}`;
  };

  const getPercentageColor = (value) => {
    if (!value && value !== 0) return "text.secondary";
    return value >= 0 ? "success.main" : "error.main";
  };

  const getPercentageIcon = (value) => {
    if (!value && value !== 0) return null;
    return value >= 0 ? (
      <TrendingUp fontSize="small" />
    ) : (
      <TrendingDown fontSize="small" />
    );
  };

  const getMarketCapTier = (marketCap) => {
    if (!marketCap) return { label: "Unknown", color: "default" };

    if (marketCap >= 10000000000) {
      // $10B+
      return { label: "Large Cap", color: "success" };
    } else if (marketCap >= 1000000000) {
      // $1B+
      return { label: "Mid Cap", color: "warning" };
    } else {
      return { label: "Small Cap", color: "error" };
    }
  };

  if (isLoading) {
    return (
      <Card sx={{ minHeight: compact ? 120 : 180 }}>
        <CardContent
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            height: "100%",
          }}
        >
          <CircularProgress size={32} />
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card sx={{ minHeight: compact ? 120 : 180 }}>
        <CardContent>
          <Alert severity="error" sx={{ mb: 1 }}>
            Failed to load {symbol} price
          </Alert>
          <Typography variant="caption" color="text.secondary">
            {error.message}
          </Typography>
        </CardContent>
      </Card>
    );
  }

  if (!priceData?.data) {
    return (
      <Card sx={{ minHeight: compact ? 120 : 180 }}>
        <CardContent>
          <Alert severity="info">No price data available for {symbol}</Alert>
        </CardContent>
      </Card>
    );
  }

  const data = priceData.data;
  const marketCapTier = getMarketCapTier(data.market_cap);

  return (
    <Card sx={{ minHeight: compact ? 120 : 180, position: "relative" }}>
      <CardContent sx={{ pb: compact ? 1 : 2 }}>
        {/* Header */}
        <Box
          display="flex"
          justifyContent="space-between"
          alignItems="flex-start"
          mb={1}
        >
          <Box>
            <Typography variant={compact ? "subtitle1" : "h6"} component="div">
              {data.symbol}
            </Typography>
            {!compact && (
              <Typography variant="caption" color="text.secondary">
                {symbol} Price
              </Typography>
            )}
          </Box>

          <Box display="flex" alignItems="center">
            {!compact && (
              <Chip
                label={marketCapTier.label}
                size="small"
                color={marketCapTier.color}
                variant="outlined"
                sx={{ mr: 1 }}
              />
            )}

            <IconButton
              size="small"
              onClick={handleMenuOpen}
              sx={{ ml: "auto" }}
            >
              <MoreVert fontSize="small" />
            </IconButton>
          </Box>
        </Box>

        {/* Price */}
        <Typography
          variant={compact ? "h6" : "h5"}
          component="div"
          color="primary"
          sx={{ fontWeight: "bold", mb: 1 }}
        >
          {formatCurrency(data.current_price)}
        </Typography>

        {/* 24h Change */}
        <Box display="flex" alignItems="center" mb={compact ? 0 : 1}>
          {getPercentageIcon(data.price_change_percentage_24h)}
          <Typography
            variant="body2"
            color={getPercentageColor(data.price_change_percentage_24h)}
            sx={{ ml: 0.5, fontWeight: "medium" }}
          >
            {formatPercentage(data.price_change_percentage_24h)} (24h)
          </Typography>
        </Box>

        {/* Additional Info (not in compact mode) */}
        {!compact && (
          <>
            <Box display="flex" justifyContent="space-between" mb={1}>
              <Typography variant="caption" color="text.secondary">
                24h High
              </Typography>
              <Typography variant="caption">
                {formatCurrency(data.high_24h)}
              </Typography>
            </Box>

            <Box display="flex" justifyContent="space-between" mb={1}>
              <Typography variant="caption" color="text.secondary">
                24h Low
              </Typography>
              <Typography variant="caption">
                {formatCurrency(data.low_24h)}
              </Typography>
            </Box>

            <Box display="flex" justifyContent="space-between" mb={1}>
              <Typography variant="caption" color="text.secondary">
                Market Cap
              </Typography>
              <Typography variant="caption">
                {formatCurrency(data.market_cap, 0)}
              </Typography>
            </Box>

            <Box display="flex" justifyContent="space-between">
              <Typography variant="caption" color="text.secondary">
                24h Volume
              </Typography>
              <Typography variant="caption">
                {formatCurrency(data.volume_24h, 0)}
              </Typography>
            </Box>
          </>
        )}

        {/* Technical Indicators (if available) */}
        {data.technical_indicators && !compact && (
          <Box mt={2}>
            <Typography variant="caption" color="text.secondary" gutterBottom>
              Technical Indicators
            </Typography>
            <Box display="flex" gap={1} flexWrap="wrap">
              <Chip
                label={`RSI: ${data.technical_indicators.rsi}`}
                size="small"
                variant="outlined"
              />
              <Chip
                label={`SMA20: ${formatCurrency(data.technical_indicators.sma_20)}`}
                size="small"
                variant="outlined"
              />
            </Box>
          </Box>
        )}
      </CardContent>

      {/* Menu */}
      <Menu
        anchorEl={anchorEl}
        open={Boolean(anchorEl)}
        onClose={handleMenuClose}
        anchorOrigin={{
          vertical: "top",
          horizontal: "right",
        }}
        transformOrigin={{
          vertical: "top",
          horizontal: "right",
        }}
      >
        <MenuItem onClick={handleRefresh}>
          <Refresh fontSize="small" sx={{ mr: 1 }} />
          Refresh
        </MenuItem>

        <MenuItem onClick={handleWatchlistToggle}>
          {isInWatchlist ? (
            <>
              <Star fontSize="small" sx={{ mr: 1 }} />
              Remove from Watchlist
            </>
          ) : (
            <>
              <StarBorder fontSize="small" sx={{ mr: 1 }} />
              Add to Watchlist
            </>
          )}
        </MenuItem>

        {showChart && (
          <MenuItem onClick={handleMenuClose}>
            <ShowChart fontSize="small" sx={{ mr: 1 }} />
            View Chart
          </MenuItem>
        )}
      </Menu>

      {/* Last Updated Indicator */}
      <Box
        position="absolute"
        bottom={4}
        right={8}
        sx={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          backgroundColor: "success.main",
          animation: "pulse 2s infinite",
        }}
      />
    </Card>
  );
}

export default CryptoPriceWidget;
