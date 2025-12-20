import {
  Box,
  Card,
  CardContent,
  Grid,
  LinearProgress,
  Typography,
  Alert,
  Paper,
} from "@mui/material";
import { useTheme, alpha } from "@mui/material/styles";

const MarketCorrelation = ({ data, isLoading, error }) => {
  const theme = useTheme();

  if (isLoading) {
    return <LinearProgress />;
  }

  if (error || !data?.data) {
    return (
      <Alert severity="error">
        Unable to load correlation data. {error?.message}
      </Alert>
    );
  }

  const { correlations, statistics, analysis } = data.data;

  // Handle case where correlations might be undefined or empty
  if (!correlations || !Array.isArray(correlations) || correlations.length === 0) {
    return (
      <Alert severity="info">
        Correlation data not yet available. Historical price data for analysis is loading.
      </Alert>
    );
  }

  const symbols = correlations.map((c) => c.symbol);

  // Get color based on correlation value
  const getCorrelationColor = (value) => {
    if (value === null || value === undefined) return theme.palette.grey[200];
    if (value === 1) return theme.palette.success.light;
    if (value > 0.7) return alpha(theme.palette.success.main, 0.6);
    if (value > 0.3) return alpha(theme.palette.info.main, 0.4);
    if (value > 0) return alpha(theme.palette.info.main, 0.2);
    if (value > -0.3) return alpha(theme.palette.warning.main, 0.2);
    if (value > -0.7) return alpha(theme.palette.error.main, 0.4);
    return alpha(theme.palette.error.main, 0.6);
  };

  const getTextColor = (value) => {
    if (value === null || value === undefined) return theme.palette.text.secondary;
    if (value >= 0.5 || value <= -0.5) return theme.palette.common.white;
    return theme.palette.text.primary;
  };

  return (
    <Box>
      <Grid container spacing={3}>
        {/* Correlation Matrix */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 3, fontWeight: 600 }}>
                Asset Correlation Matrix
              </Typography>

              <Box sx={{ overflowX: "auto" }}>
                <Paper elevation={0} sx={{ p: 2, bgcolor: "grey.50" }}>
                  <table
                    style={{
                      width: "100%",
                      borderCollapse: "collapse",
                      minWidth: "600px",
                    }}
                  >
                    <thead>
                      <tr>
                        <th
                          style={{
                            padding: "8px",
                            textAlign: "left",
                            fontWeight: 600,
                            borderBottom: `2px solid ${theme.palette.divider}`,
                          }}
                        >
                          Symbol
                        </th>
                        {symbols.map((sym) => (
                          <th
                            key={sym}
                            style={{
                              padding: "8px",
                              textAlign: "center",
                              fontWeight: 600,
                              fontSize: "0.85rem",
                              borderBottom: `2px solid ${theme.palette.divider}`,
                            }}
                          >
                            {sym}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {correlations.map((row, rowIdx) => (
                        <tr key={row.symbol}>
                          <td
                            style={{
                              padding: "8px",
                              fontWeight: 600,
                              borderRight: `1px solid ${theme.palette.divider}`,
                            }}
                          >
                            {row.symbol}
                          </td>
                          {row.correlations.map((corrValue, colIdx) => (
                            <td
                              key={`${rowIdx}-${colIdx}`}
                              style={{
                                padding: "8px",
                                textAlign: "center",
                                backgroundColor: getCorrelationColor(corrValue),
                                color: getTextColor(corrValue),
                                fontWeight: corrValue !== null ? 600 : 400,
                                fontSize: "0.85rem",
                                border: `1px solid ${theme.palette.divider}`,
                              }}
                            >
                              {corrValue === null || corrValue === undefined
                                ? "—"
                                : (() => {
                                    const num = typeof corrValue === 'number' ? corrValue : parseFloat(corrValue) || 0;
                                    return isNaN(num) ? "—" : num.toFixed(2);
                                  })()}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </Paper>
              </Box>

              <Box sx={{ mt: 3, p: 2, bgcolor: "grey.50", borderRadius: 1 }}>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  <strong>Color Scale:</strong> Green = Highly Correlated | Blue = Moderately
                  Correlated | Gray = No Correlation | Red = Negatively Correlated
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  <strong>Note:</strong> Diagonal is always 1.0 (perfect correlation with itself).
                  Null values indicate insufficient data.
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Statistics & Analysis */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                Correlation Statistics
              </Typography>

              <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <Box sx={{ p: 2, bgcolor: "grey.50", borderRadius: 1 }}>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
                    Average Correlation
                  </Typography>
                  <Typography variant="h6" sx={{ fontWeight: 600 }}>
                    {statistics.avg_correlation !== null
                      ? (() => {
                          const num = typeof statistics.avg_correlation === 'number' ? statistics.avg_correlation : parseFloat(statistics.avg_correlation) || 0;
                          return isNaN(num) ? "N/A" : num.toFixed(2);
                        })()
                      : "N/A"}
                  </Typography>
                </Box>

                <Box sx={{ p: 2, bgcolor: "grey.50", borderRadius: 1 }}>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
                    Maximum Correlation
                  </Typography>
                  <Typography variant="h6" sx={{ fontWeight: 600 }}>
                    {statistics.max_correlation?.value !== null
                      ? (() => {
                          const num = typeof statistics.max_correlation.value === 'number' ? statistics.max_correlation.value : parseFloat(statistics.max_correlation.value) || 0;
                          return isNaN(num) ? "N/A" : num.toFixed(2);
                        })()
                      : "N/A"}
                    {statistics.max_correlation?.pair?.length === 2 && (
                      <Typography variant="caption" color="text.secondary" sx={{ ml: 1 }}>
                        ({statistics.max_correlation.pair.join(" & ")})
                      </Typography>
                    )}
                  </Typography>
                </Box>

                <Box sx={{ p: 2, bgcolor: "grey.50", borderRadius: 1 }}>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
                    Minimum Correlation
                  </Typography>
                  <Typography variant="h6" sx={{ fontWeight: 600 }}>
                    {statistics.min_correlation?.value !== null
                      ? (() => {
                          const num = typeof statistics.min_correlation.value === 'number' ? statistics.min_correlation.value : parseFloat(statistics.min_correlation.value) || 0;
                          return isNaN(num) ? "N/A" : num.toFixed(2);
                        })()
                      : "N/A"}
                    {statistics.min_correlation?.pair?.length === 2 && (
                      <Typography variant="caption" color="text.secondary" sx={{ ml: 1 }}>
                        ({statistics.min_correlation.pair.join(" & ")})
                      </Typography>
                    )}
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Portfolio Analysis */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                Portfolio Analysis
              </Typography>

              <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <Box sx={{ p: 2, bgcolor: "grey.50", borderRadius: 1 }}>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
                    Market Regime
                  </Typography>
                  <Typography variant="h6" sx={{ fontWeight: 600 }}>
                    {analysis?.market_regime || "N/A"}
                  </Typography>
                </Box>

                <Box sx={{ p: 2, bgcolor: "grey.50", borderRadius: 1 }}>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
                    Diversification Score
                  </Typography>
                  <Typography variant="h6" sx={{ fontWeight: 600 }}>
                    {analysis?.diversification_score !== null
                      ? (() => {
                          const num = typeof analysis.diversification_score === 'number' ? analysis.diversification_score : parseFloat(analysis.diversification_score) || 0;
                          return isNaN(num) ? "N/A" : num.toFixed(1);
                        })()
                      : "N/A"}
                  </Typography>
                </Box>

                <Box sx={{ p: 2, bgcolor: "grey.50", borderRadius: 1 }}>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                    Risk Assessment:
                  </Typography>
                  {analysis?.risk_assessment && (
                    <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
                      <Typography variant="caption">
                        • <strong>Concentration:</strong>{" "}
                        {analysis.risk_assessment.concentration_risk}
                      </Typography>
                      <Typography variant="caption">
                        • <strong>Diversification:</strong>{" "}
                        {analysis.risk_assessment.diversification_benefit}
                      </Typography>
                      <Typography variant="caption">
                        • <strong>Stability:</strong>{" "}
                        {analysis.risk_assessment.portfolio_stability}
                      </Typography>
                    </Box>
                  )}
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
};

export default MarketCorrelation;
