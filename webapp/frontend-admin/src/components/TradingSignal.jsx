import { Chip, Tooltip, _Box } from "@mui/material";
import { TrendingUp, TrendingDown, Remove } from "@mui/icons-material";

/**
 * TradingSignal Component
 * Displays trading signals (BUY, SELL, HOLD) with visual indicators
 */
export default function TradingSignal({
  signal = "HOLD",
  confidence = 0.75,
  size = "small",
  variant = "filled",
  showConfidence = true,
}) {
  const getSignalColor = () => {
    switch (signal?.toUpperCase()) {
      case "BUY":
        return "success";
      case "SELL":
        return "error";
      case "HOLD":
      default:
        return "warning";
    }
  };

  const getSignalIcon = () => {
    switch (signal?.toUpperCase()) {
      case "BUY":
        return <TrendingUp />;
      case "SELL":
        return <TrendingDown />;
      case "HOLD":
      default:
        return <Remove />;
    }
  };

  const label = showConfidence
    ? `${signal} (${(confidence * 100).toFixed(0)}%)`
    : signal;

  return (
    <Tooltip
      title={`Signal: ${signal} | Confidence: ${(confidence * 100).toFixed(1)}%`}
      arrow
    >
      <Chip
        icon={getSignalIcon()}
        label={label}
        color={getSignalColor()}
        size={size}
        variant={variant}
        sx={{
          fontWeight: 600,
          minWidth: variant === "outlined" ? "auto" : "100px",
        }}
      />
    </Tooltip>
  );
}
