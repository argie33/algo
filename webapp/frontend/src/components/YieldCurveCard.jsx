import { Card, CardContent, Box, Typography, Chip, CircularProgress, useTheme, alpha } from "@mui/material";
import { TrendingUp, TrendingDown, Warning } from "@mui/icons-material";

const YieldCurveCard = ({ data, isLoading = false }) => {
  const theme = useTheme();

  if (isLoading) {
    return (
      <Card sx={{
        background: theme.palette.background.paper,
        backdropFilter: "blur(10px)",
        border: `1px solid ${alpha(theme.palette.primary.main, 0.1)}`,
      }}>
        <CardContent sx={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "200px" }}>
          <CircularProgress />
        </CardContent>
      </Card>
    );
  }

  if (!data || !data.spread_10y_2y) {
    return (
      <Card sx={{
        background: theme.palette.background.paper,
        backdropFilter: "blur(10px)",
        border: `1px solid ${alpha(theme.palette.primary.main, 0.1)}`,
      }}>
        <CardContent>
          <Typography color="textSecondary">No yield curve data available</Typography>
        </CardContent>
      </Card>
    );
  }

  const spread = data.spread_10y_2y;
  const isInverted = data.is_inverted;
  const isNegative = spread < 0;

  return (
    <Card
      sx={{
        background: isInverted
          ? alpha(theme.palette.error.main, 0.1)
          : alpha(theme.palette.success.main, 0.05),
        border: `1px solid ${isInverted ? alpha(theme.palette.error.main, 0.3) : alpha(theme.palette.success.main, 0.3)}`,
        backdropFilter: "blur(10px)",
        transition: "all 0.3s ease",
        "&:hover": {
          boxShadow: theme.shadows[4],
        }
      }}
    >
      <CardContent>
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", mb: 2 }}>
          <Box>
            <Typography variant="subtitle2" sx={{ opacity: 0.8, fontWeight: 500 }}>
              Yield Curve (10Y-2Y Spread)
            </Typography>
            <Typography variant="h4" sx={{ my: 1, fontWeight: 700 }}>
              {Math.abs(spread).toFixed(2)}%
            </Typography>
          </Box>
          {isInverted && (
            <Chip
              icon={<Warning />}
              label="INVERTED"
              color="error"
              size="small"
              variant="outlined"
            />
          )}
        </Box>

        <Box sx={{ display: "flex", gap: 2, mb: 2, flexWrap: "wrap" }}>
          <Box>
            <Typography variant="caption" sx={{ opacity: 0.7, display: "block" }}>
              10Y Treasury
            </Typography>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              {data.tnx_10y?.toFixed(2)}%
            </Typography>
          </Box>
          <Box>
            <Typography variant="caption" sx={{ opacity: 0.7, display: "block" }}>
              2Y Treasury
            </Typography>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              {data.irx_2y?.toFixed(2)}%
            </Typography>
          </Box>
        </Box>

        <Box sx={{
          p: 1.5,
          bgcolor: alpha(theme.palette.info.main, 0.1),
          borderRadius: 1,
          border: `1px solid ${alpha(theme.palette.info.main, 0.2)}`
        }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
            {isNegative ? (
              <TrendingDown sx={{ color: theme.palette.error.main, fontSize: "1.2rem" }} />
            ) : (
              <TrendingUp sx={{ color: theme.palette.success.main, fontSize: "1.2rem" }} />
            )}
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              {isInverted ? "Yield Curve INVERTED" : "Yield Curve NORMAL"}
            </Typography>
          </Box>
          <Typography variant="caption" sx={{ opacity: 0.8 }}>
            {isInverted
              ? "Inverted yield curves historically signal recession risk"
              : "Normal yield curve suggests economic expansion"
            }
          </Typography>
        </Box>

        {data.date && (
          <Typography variant="caption" sx={{ opacity: 0.6, display: "block", mt: 1 }}>
            As of {new Date(data.date).toLocaleDateString()}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
};

export default YieldCurveCard;
