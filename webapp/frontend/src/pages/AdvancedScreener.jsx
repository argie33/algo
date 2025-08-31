import { useState } from "react";
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  Button,
  CircularProgress,
  Alert,
} from "@mui/material";
import { Search } from "@mui/icons-material";

const AdvancedScreener = () => {
  const [_screenCriteria] = useState({
    quality: [0, 100],
    growth: [0, 100],
    value: [0, 100],
    momentum: [0, 100],
    sentiment: [0, 100],
    positioning: [0, 100],
    marketCap: "any",
    sector: "any",
    exchange: "any",
    dividendYield: [0, 20],
    pe: [0, 50],
    pb: [0, 10],
    roe: [0, 50],
    debt: [0, 5],
    volume: [0, 1000000],
    price: [0, 1000],
    beta: [0, 3],
    esgScore: [0, 100],
  });

  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const mockResults = [
    {
      symbol: "AAPL",
      company: "Apple Inc.",
      price: 175.43,
      marketCap: "2.8T",
      sector: "Technology",
      pe: 28.5,
      pb: 12.3,
      roe: 0.75,
      dividendYield: 0.48,
      beta: 1.2,
      esgScore: 85,
      scores: {
        composite: 85,
        quality: 90,
        growth: 80,
        value: 75,
        momentum: 85,
        sentiment: 88,
        positioning: 82,
      },
    },
  ];

  const runScreen = async () => {
    setLoading(true);
    setError(null);

    try {
      // Simulate API call
      await new Promise((resolve) => setTimeout(resolve, 1000));
      setResults(mockResults);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Container maxWidth="xl" sx={{ py: 3 }}>
      <Box sx={{ mb: 4 }}>
        <Typography
          variant="h4"
          component="h1"
          gutterBottom
          sx={{ fontWeight: 700, color: "primary.main" }}
        >
          📊 Advanced Stock Screener
        </Typography>
        <Typography variant="subtitle1" color="text.secondary">
          Find stocks that match your investment criteria with advanced
          filtering
        </Typography>
      </Box>

      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} md={6}>
              <Button
                variant="contained"
                onClick={runScreen}
                disabled={loading}
                startIcon={
                  loading ? <CircularProgress size={20} /> : <Search />
                }
                fullWidth
              >
                {loading ? "Screening..." : "Run Screen"}
              </Button>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          Error: {error}
        </Alert>
      )}

      {results.length > 0 && (
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Screening Results ({(results?.length || 0)} stocks found)
            </Typography>
            <Grid container spacing={2}>
              {(results || []).map((stock) => (
                <Grid item xs={12} md={6} lg={4} key={stock.symbol}>
                  <Card variant="outlined">
                    <CardContent>
                      <Typography variant="h6">{stock.symbol}</Typography>
                      <Typography variant="body2" color="text.secondary">
                        {stock.company}
                      </Typography>
                      <Typography variant="h5">${stock.price}</Typography>
                    </CardContent>
                  </Card>
                </Grid>
              ))}
            </Grid>
          </CardContent>
        </Card>
      )}
    </Container>
  );
};

export default AdvancedScreener;
