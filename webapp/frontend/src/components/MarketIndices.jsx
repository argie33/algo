import {
  Box,
  Card,
  CardContent,
  Grid,
  LinearProgress,
  Typography,
  Alert,
  Paper,
  Chip,
} from "@mui/material";
import { TrendingUp, TrendingDown } from "@mui/icons-material";
import { useTheme, alpha } from "@mui/material/styles";

const MarketIndices = ({ data, isLoading, error }) => {
  const theme = useTheme();

  if (isLoading) {
    return <LinearProgress />;
  }

  if (error) {
    return (
      <Alert severity="error">
        Unable to load market indices data. {error?.message}
      </Alert>
    );
  }

  // Display actual data from backend
  if (data && Array.isArray(data) && data.length > 0) {
    return (
      <Grid container spacing={3}>
        {data.map((index) => (
          <Grid item xs={12} sm={6} md={4} key={index.symbol}>
            <Card>
              <CardContent>
                <Typography variant="h6" sx={{ fontWeight: 600, mb: 2 }}>
                  {index.name}
                </Typography>
                <Typography variant="body2" sx={{ mb: 1 }}>
                  <strong>Symbol:</strong> {index.symbol}
                </Typography>
                <Typography variant="body2" sx={{ mb: 1 }}>
                  <strong>Price:</strong> ${index.price}
                </Typography>
                <Typography
                  variant="body2"
                  sx={{
                    mb: 2,
                    color: index.changePercent >= 0 ? "success.main" : "error.main"
                  }}
                >
                  <strong>Change:</strong> {index.changePercent}% ({index.change >= 0 ? '+' : ''}{index.change})
                </Typography>

                {/* Valuation Metrics */}
                {index.pe && (
                  <Box sx={{ pt: 2, borderTop: 1, borderColor: "divider" }}>
                    <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                      Valuation Metrics
                    </Typography>
                    <Typography variant="caption" sx={{ display: "block", mb: 0.5 }}>
                      <strong>Trailing P/E:</strong> {index.pe.trailing}
                    </Typography>
                    <Typography variant="caption" sx={{ display: "block", mb: 0.5 }}>
                      <strong>Forward P/E:</strong> {index.pe.forward}
                    </Typography>
                    {index.pe.priceToBook && (
                      <Typography variant="caption" sx={{ display: "block", mb: 0.5 }}>
                        <strong>P/B Ratio:</strong> {index.pe.priceToBook}
                      </Typography>
                    )}
                    {index.pe.priceToSales && (
                      <Typography variant="caption" sx={{ display: "block", mb: 0.5 }}>
                        <strong>P/S Ratio:</strong> {index.pe.priceToSales}
                      </Typography>
                    )}
                    {index.pe.dividendYield && (
                      <Typography variant="caption" sx={{ display: "block", fontSize: "0.75rem", color: "text.secondary" }}>
                        <strong>Dividend Yield:</strong> {index.pe.dividendYield}%
                      </Typography>
                    )}
                  </Box>
                )}
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
    );
  }

  // Fallback placeholder
  const majorIndices = [
    { symbol: "^GSPC", name: "S&P 500", sector: "Broad Market" },
    { symbol: "^IXIC", name: "NASDAQ Composite", sector: "Technology Heavy" },
    { symbol: "^DJI", name: "Dow Jones Industrial", sector: "Large Cap" },
    { symbol: "^RUT", name: "Russell 2000", sector: "Small Cap" },
  ];

  return (
    <Box>
      <Alert severity="info" sx={{ mb: 3 }}>
        📊 <strong>Market Indices</strong> - Real-time market index data
      </Alert>

      <Grid container spacing={3}>
        {/* Major Indices Overview */}
        <Grid item xs={12}>
          <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
            Major Global Indices
          </Typography>

          <Grid container spacing={2}>
            {majorIndices.map((index) => (
              <Grid item xs={12} sm={6} md={4} key={index.symbol}>
                <Card sx={{ height: "100%" }}>
                  <CardContent>
                    <Box sx={{ mb: 2 }}>
                      <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 0.5 }}>
                        {index.sector}
                      </Typography>
                      <Typography variant="h6" sx={{ fontWeight: 600, mb: 0.5 }}>
                        {index.name}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {index.symbol}
                      </Typography>
                    </Box>

                    <Box
                      sx={{
                        p: 2,
                        bgcolor: alpha(theme.palette.primary.main, 0.05),
                        borderRadius: 1,
                        textAlign: "center",
                      }}
                    >
                      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                        Price
                      </Typography>
                      <Typography variant="h5" sx={{ fontWeight: 600, color: "text.primary" }}>
                        —
                      </Typography>
                      <Typography variant="caption" color="text.secondary" sx={{ mt: 1 }}>
                        Real-time data coming soon
                      </Typography>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Grid>
      </Grid>
    </Box>
  );
};

export default MarketIndices;
