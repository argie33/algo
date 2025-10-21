import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Box,
  Card,
  CardContent,
  Container,
  Grid,
  Paper,
  Tab,
  Tabs,
  Typography,
  CircularProgress,
  Alert,
  Chip,
  useTheme,
  alpha,
} from "@mui/material";
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { TrendingUp, TrendingDown, ShowChart } from "@mui/icons-material";
import { getMarketSentimentHistory } from "../services/api";

// Sentiment Gauge Component
const SentimentGauge = ({ label, value, min = 0, max = 100 }) => {
  const theme = useTheme();
  const percentage = ((value - min) / (max - min)) * 100;

  // Determine color based on value
  let color = theme.palette.warning.main;
  let sentiment = "Neutral";

  if (percentage > 75) {
    color = theme.palette.success.main;
    sentiment = "Very Bullish";
  } else if (percentage > 60) {
    color = theme.palette.success.light;
    sentiment = "Bullish";
  } else if (percentage > 40) {
    color = theme.palette.warning.main;
    sentiment = "Neutral";
  } else if (percentage > 25) {
    color = theme.palette.warning.light;
    sentiment = "Bearish";
  } else {
    color = theme.palette.error.main;
    sentiment = "Very Bearish";
  }

  return (
    <Card sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <CardContent sx={{ textAlign: "center", flex: 1 }}>
        <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
          {label}
        </Typography>

        {/* Circular Gauge */}
        <Box
          sx={{
            position: "relative",
            width: 200,
            height: 200,
            margin: "0 auto 20px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {/* Background circle */}
          <svg
            width={200}
            height={200}
            style={{ position: "absolute", transform: "rotate(-90deg)" }}
          >
            <circle
              cx={100}
              cy={100}
              r={80}
              fill="none"
              stroke={alpha(theme.palette.divider, 0.2)}
              strokeWidth={8}
            />
            {/* Progress arc */}
            <circle
              cx={100}
              cy={100}
              r={80}
              fill="none"
              stroke={color}
              strokeWidth={8}
              strokeDasharray={`${(percentage / 100) * 503} 503`}
              style={{ transition: "stroke-dasharray 0.3s ease" }}
            />
          </svg>

          {/* Center value */}
          <Box
            sx={{
              textAlign: "center",
              position: "relative",
              zIndex: 1,
            }}
          >
            <Typography
              variant="h3"
              sx={{ fontWeight: 700, color: color }}
            >
              {Math.round(value)}
            </Typography>
            <Typography variant="caption" sx={{ color: theme.palette.text.secondary }}>
              {sentiment}
            </Typography>
          </Box>
        </Box>

        {/* Range indicator */}
        <Box sx={{ mt: 3 }}>
          <Box
            sx={{
              width: "100%",
              height: 8,
              backgroundColor: alpha(theme.palette.divider, 0.2),
              borderRadius: 4,
              overflow: "hidden",
              mb: 1,
            }}
          >
            <Box
              sx={{
                width: `${percentage}%`,
                height: "100%",
                backgroundColor: color,
                transition: "width 0.3s ease",
              }}
            />
          </Box>
          <Box sx={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem" }}>
            <span>Bearish</span>
            <span>Bullish</span>
          </Box>
        </Box>
      </CardContent>
    </Card>
  );
};

// Sentiment Factor Card
const SentimentFactor = ({ icon: Icon, label, value, description }) => {
  const theme = useTheme();
  const isPositive = value > 0;

  return (
    <Card
      sx={{
        background: `linear-gradient(135deg, ${alpha(
          isPositive ? theme.palette.success.main : theme.palette.error.main,
          0.1
        )} 0%, ${alpha(theme.palette.background.paper, 0)} 100%)`,
      }}
    >
      <CardContent>
        <Box sx={{ display: "flex", alignItems: "center", mb: 1 }}>
          <Icon
            sx={{
              mr: 1,
              color: isPositive ? theme.palette.success.main : theme.palette.error.main,
            }}
          />
          <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
            {label}
          </Typography>
        </Box>
        <Typography
          variant="h5"
          sx={{
            color: isPositive ? theme.palette.success.main : theme.palette.error.main,
            fontWeight: 700,
            mb: 0.5,
          }}
        >
          {Math.abs(value).toFixed(1)}%
        </Typography>
        <Typography variant="caption" sx={{ color: theme.palette.text.secondary }}>
          {description}
        </Typography>
      </CardContent>
    </Card>
  );
};

function TabPanel(props) {
  const { children, value, index, ...other } = props;
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`sentiment-tabpanel-${index}`}
      aria-labelledby={`sentiment-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ py: 2 }}>{children}</Box>}
    </div>
  );
}

export default function SentimentPage() {
  const theme = useTheme();
  const [tabValue, setTabValue] = useState(0);

  // Fetch market sentiment data
  const { data: marketSentimentData, isLoading: isLoadingMarket } = useQuery({
    queryKey: ["marketSentiment"],
    queryFn: () => getMarketSentimentHistory(30),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  // Calculate sentiment metrics from the fetched data - REAL DATA ONLY
  const aaii = marketSentimentData?.data?.[0]?.bullish ? parseFloat(marketSentimentData.data[0].bullish) : null;
  const neutral = marketSentimentData?.data?.[0]?.neutral ? parseFloat(marketSentimentData.data[0].neutral) : null;
  const bearish = marketSentimentData?.data?.[0]?.bearish ? parseFloat(marketSentimentData.data[0].bearish) : null;

  const sentimentData = {
    marketSentiment: {
      aaii: aaii,
      neutral: neutral,
      bearish: bearish,
    },
    historicalTrend: (marketSentimentData?.data || []).map((item) => ({
      date: new Date(item.date).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric"
      }),
      bullish: parseFloat(item.bullish) || null,
      neutral: parseFloat(item.neutral) || null,
      bearish: parseFloat(item.bearish) || null,
    })),
  };

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h3" sx={{ fontWeight: 700, mb: 1 }}>
          Market Sentiment Analysis
        </Typography>
        <Typography variant="body1" sx={{ color: theme.palette.text.secondary }}>
          Real-time sentiment indicators and trend analysis
        </Typography>
      </Box>

      {/* Loading State */}
      {isLoadingMarket && (
        <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
          <CircularProgress />
        </Box>
      )}

      {!isLoadingMarket && (
      <>

      {/* Overall Sentiment Score */}
      <Card sx={{ mb: 4, background: `linear-gradient(135deg, ${alpha(theme.palette.primary.main, 0.1)} 0%, ${alpha(theme.palette.secondary.main, 0.1)} 100%)` }}>
        <CardContent>
          <Grid container spacing={3} alignItems="center">
            <Grid item xs={12} md={6}>
              <Typography variant="h5" sx={{ mb: 2, fontWeight: 600 }}>
                AAII Investor Sentiment
              </Typography>
              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" sx={{ color: theme.palette.text.secondary, mb: 1 }}>
                  American Association of Individual Investors bullish sentiment indicator
                </Typography>
                <Box sx={{ display: "flex", alignItems: "center", mb: 1 }}>
                  <Typography variant="body2" sx={{ mr: 1 }}>
                    Bullish:
                  </Typography>
                  <Chip
                    label={`${sentimentData.marketSentiment.aaii ? Math.round(sentimentData.marketSentiment.aaii * 100) / 100 : "N/A"}%`}
                    color={sentimentData.marketSentiment.aaii > 50 ? "success" : "warning"}
                    variant="filled"
                  />
                </Box>
              </Box>
            </Grid>
            <Grid item xs={12} md={6}>
              <Box
                sx={{
                  display: "flex",
                  justifyContent: "space-around",
                  textAlign: "center",
                }}
              >
                <Box>
                  <Typography variant="h6" sx={{ fontWeight: 700, color: theme.palette.success.main }}>
                    {sentimentData.marketSentiment.bullish ? Math.round(sentimentData.marketSentiment.aaii * 100) / 100 : "N/A"}%
                  </Typography>
                  <Typography variant="caption">Bullish</Typography>
                </Box>
                <Box>
                  <Typography variant="h6" sx={{ fontWeight: 700, color: theme.palette.warning.main }}>
                    {sentimentData.marketSentiment.neutral ? Math.round(sentimentData.marketSentiment.neutral * 100) / 100 : "N/A"}%
                  </Typography>
                  <Typography variant="caption">Neutral</Typography>
                </Box>
                <Box>
                  <Typography variant="h6" sx={{ fontWeight: 700, color: theme.palette.error.main }}>
                    {sentimentData.marketSentiment.bearish ? Math.round(sentimentData.marketSentiment.bearish * 100) / 100 : "N/A"}%
                  </Typography>
                  <Typography variant="caption">Bearish</Typography>
                </Box>
              </Box>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Tabs */}
      <Box sx={{ mb: 3, borderBottom: 1, borderColor: "divider" }}>
        <Tabs
          value={tabValue}
          onChange={handleTabChange}
          aria-label="sentiment tabs"
        >
          <Tab label="Gauges" id="sentiment-tab-0" aria-controls="sentiment-tabpanel-0" />
          <Tab label="Factors" id="sentiment-tab-1" aria-controls="sentiment-tabpanel-1" />
          <Tab label="Trends" id="sentiment-tab-2" aria-controls="sentiment-tabpanel-2" />
        </Tabs>
      </Box>

      {/* Tab: Gauges */}
      <TabPanel value={tabValue} index={0}>
        {sentimentData.marketSentiment.aaii !== null ? (
          <Grid container spacing={3}>
            <Grid item xs={12} md={6} lg={4}>
              <SentimentGauge
                label="AAII Bullish %"
                value={sentimentData.marketSentiment.aaii}
                max={100}
              />
            </Grid>
            <Grid item xs={12} md={6} lg={4}>
              <Card sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
                <CardContent sx={{ textAlign: "center", flex: 1 }}>
                  <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                    Neutral %
                  </Typography>
                  <Typography variant="h3" sx={{ fontWeight: 700, color: theme.palette.warning.main }}>
                    {sentimentData.marketSentiment.neutral ? Math.round(sentimentData.marketSentiment.neutral * 100) / 100 : "N/A"}%
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={6} lg={4}>
              <Card sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
                <CardContent sx={{ textAlign: "center", flex: 1 }}>
                  <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                    Bearish %
                  </Typography>
                  <Typography variant="h3" sx={{ fontWeight: 700, color: theme.palette.error.main }}>
                    {sentimentData.marketSentiment.bearish ? Math.round(sentimentData.marketSentiment.bearish * 100) / 100 : "N/A"}%
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        ) : (
          <Alert severity="info">
            AAII sentiment data not available. Please ensure the data loader has been executed.
          </Alert>
        )}
      </TabPanel>

      {/* Tab: Data Sources - Coming Soon */}
      <TabPanel value={tabValue} index={1}>
        <Alert severity="info" sx={{ mb: 3 }}>
          Additional sentiment indicators (Fear & Greed Index, NAAIM Manager Exposure, etc.) are coming soon.
          Currently displaying AAII investor sentiment data.
        </Alert>
        <Card sx={{ background: alpha(theme.palette.info.main, 0.05) }}>
          <CardContent>
            <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
              📊 Available Data Sources
            </Typography>
            <Box component="ul" sx={{ m: 0, pl: 2 }}>
              <li>
                <Typography variant="body2" sx={{ mb: 1 }}>
                  <strong>AAII Investor Sentiment</strong> - Bullish, Neutral, and Bearish percentages from American Association of Individual Investors
                </Typography>
              </li>
              <li>
                <Typography variant="body2" sx={{ mb: 1 }}>
                  <strong>Coming Soon:</strong> Fear & Greed Index (CNN)
                </Typography>
              </li>
              <li>
                <Typography variant="body2" sx={{ mb: 1 }}>
                  <strong>Coming Soon:</strong> NAAIM Manager Exposure Index
                </Typography>
              </li>
              <li>
                <Typography variant="body2">
                  <strong>Coming Soon:</strong> Sentiment input factors (Technical, Fundamental, Insider, etc.)
                </Typography>
              </li>
            </Box>
          </CardContent>
        </Card>
      </TabPanel>

      {/* Tab: Trends */}
      <TabPanel value={tabValue} index={2}>
        {sentimentData.historicalTrend && sentimentData.historicalTrend.length > 0 ? (
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 3, fontWeight: 600 }}>
                AAII Sentiment History ({sentimentData.historicalTrend.length} days)
              </Typography>
              <ResponsiveContainer width="100%" height={300}>
                <AreaChart data={sentimentData.historicalTrend}>
                  <CartesianGrid strokeDasharray="3 3" stroke={alpha(theme.palette.divider, 0.2)} />
                  <XAxis dataKey="date" tick={{ fontSize: 12, fill: theme.palette.text.secondary }} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 12, fill: theme.palette.text.secondary }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: alpha(theme.palette.background.paper, 0.95),
                      border: `1px solid ${theme.palette.divider}`,
                      borderRadius: 8,
                    }}
                  />
                  <Legend wrapperStyle={{ paddingTop: 20 }} />
                  <Area
                    type="monotone"
                    dataKey="bullish"
                    name="Bullish %"
                    stroke={theme.palette.success.main}
                    fill={alpha(theme.palette.success.main, 0.2)}
                    stackId="1"
                  />
                  <Area
                    type="monotone"
                    dataKey="neutral"
                    name="Neutral %"
                    stroke={theme.palette.warning.main}
                    fill={alpha(theme.palette.warning.main, 0.2)}
                    stackId="1"
                  />
                  <Area
                    type="monotone"
                    dataKey="bearish"
                    name="Bearish %"
                    stroke={theme.palette.error.main}
                    fill={alpha(theme.palette.error.main, 0.2)}
                    stackId="1"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        ) : (
          <Alert severity="info">
            Historical sentiment data not available. The chart will display once data is loaded.
          </Alert>
        )}
      </TabPanel>

      {/* Info Card */}
      <Alert severity="info" sx={{ mt: 4 }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
          📊 About AAII Sentiment
        </Typography>
        <Typography variant="body2">
          The American Association of Individual Investors (AAII) Sentiment Survey is a weekly survey that measures the percentage of individual investors who are bullish, neutral, and bearish on the stock market for the next 6 months. It serves as a contrarian indicator - extreme readings often signal reversals in market direction.
        </Typography>
      </Alert>
      </>
      )}
    </Container>
  );
}
