import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Box,
  Typography,
  Grid,
  Card,
  CardContent,
  CardHeader,
  Paper,
  Tabs,
  Tab,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Chip,
  Avatar,
  LinearProgress,
  Alert,
  Button,
  Divider,
  List,
  ListItem,
  ListItemText,
  ListItemAvatar,
} from "@mui/material";
import {
  TrendingUp,
  TrendingDown,
  Event,
  Star,
  BookmarkBorder,
  Share,
  ThumbUp,
  Comment,
  Visibility,
} from "@mui/icons-material";
import {
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  AreaChart,
  Area,
} from "recharts";
import {
  getMarketCommentary,
  getMarketTrends,
  getAnalystOpinions,
  subscribeToCommentary,
} from "../services/api";
import ErrorBoundary from "../components/ErrorBoundary";

const MarketCommentary = () => {
  const [activeTab, setActiveTab] = useState(0);
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [timePeriod, setTimePeriod] = useState("week");

  // Market commentary data
  const {
    data: commentaryData,
    isLoading: commentaryLoading,
    error: commentaryError,
  } = useQuery({
    queryKey: ["marketCommentary", selectedCategory, timePeriod],
    queryFn: () => getMarketCommentary(selectedCategory, timePeriod),
    staleTime: 300000, // 5 minutes
    retry: 2,
  });

  // Market trends data
  const { data: trendsData, isLoading: _trendsLoading } = useQuery({
    queryKey: ["marketTrends", timePeriod],
    queryFn: () => getMarketTrends(timePeriod),
    staleTime: 300000,
  });

  // Analyst opinions
  const { data: analystsData, isLoading: analystsLoading } = useQuery({
    queryKey: ["analystOpinions"],
    queryFn: () => getAnalystOpinions(),
    staleTime: 600000, // 10 minutes
  });

  const handleTabChange = (event, newValue) => {
    setActiveTab(newValue);
  };

  const handleCategoryChange = (event) => {
    setSelectedCategory(event.target.value);
  };

  const handleTimePeriodChange = (event) => {
    setTimePeriod(event.target.value);
  };

  const handleSubscribe = async () => {
    try {
      await subscribeToCommentary(selectedCategory);
      // Show success message
    } catch (error) {
      console.error("Failed to subscribe to commentary:", error);
    }
  };

  const renderLoadingState = () => (
    <Box sx={{ p: 3 }}>
      <LinearProgress sx={{ mb: 2 }} />
      <Typography>Loading market commentary...</Typography>
    </Box>
  );

  const renderErrorState = () => (
    <Alert severity="error" sx={{ m: 2 }}>
      Unable to load market commentary data. Please try again later.
    </Alert>
  );

  const renderCommentaryCard = (commentary) => (
    <Card key={commentary.id} sx={{ mb: 2, "&:hover": { boxShadow: 6 } }}>
      <CardHeader
        avatar={
          <Avatar
            sx={{
              bgcolor:
                commentary.sentiment === "bullish"
                  ? "success.main"
                  : commentary.sentiment === "bearish"
                    ? "error.main"
                    : "warning.main",
            }}
          >
            {commentary.author.charAt(0)}
          </Avatar>
        }
        title={commentary.title}
        subheader={
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 1 }}>
            <Typography variant="caption" color="textSecondary">
              {commentary.author} •{" "}
              {new Date(commentary.publishedAt).toLocaleDateString()}
            </Typography>
            <Chip
              label={commentary.category}
              size="small"
              variant="outlined"
              color="primary"
            />
            <Chip
              label={commentary.sentiment}
              size="small"
              color={
                commentary.sentiment === "bullish"
                  ? "success"
                  : commentary.sentiment === "bearish"
                    ? "error"
                    : "warning"
              }
              icon={
                commentary.sentiment === "bullish" ? (
                  <TrendingUp />
                ) : (
                  <TrendingDown />
                )
              }
            />
          </Box>
        }
        action={
          <Box>
            <Button size="small" startIcon={<BookmarkBorder />}>
              Save
            </Button>
            <Button size="small" startIcon={<Share />}>
              Share
            </Button>
          </Box>
        }
      />
      <CardContent>
        <Typography variant="body2" color="textSecondary" paragraph>
          {commentary.summary}
        </Typography>
        <Typography variant="body1" paragraph>
          {commentary.content.substring(0, 300)}...
        </Typography>
        <Box sx={{ display: "flex", alignItems: "center", gap: 2, mt: 2 }}>
          <Button size="small" startIcon={<ThumbUp />}>
            {commentary.likes}
          </Button>
          <Button size="small" startIcon={<Comment />}>
            {commentary.comments}
          </Button>
          <Button size="small" startIcon={<Visibility />}>
            {commentary.views}
          </Button>
        </Box>
      </CardContent>
    </Card>
  );

  const renderTrendsChart = () => {
    if (!trendsData?.trends) return null;

    return (
      <Paper sx={{ p: 3, mb: 3 }}>
        <Typography variant="h6" gutterBottom>
          Market Trends Overview
        </Typography>
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={trendsData.trends}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" />
            <YAxis />
            <Tooltip />
            <Legend />
            <Area
              type="monotone"
              dataKey="bullish"
              stackId="1"
              stroke="#4caf50"
              fill="#4caf50"
              fillOpacity={0.6}
            />
            <Area
              type="monotone"
              dataKey="bearish"
              stackId="1"
              stroke="#f44336"
              fill="#f44336"
              fillOpacity={0.6}
            />
            <Area
              type="monotone"
              dataKey="neutral"
              stackId="1"
              stroke="#ff9800"
              fill="#ff9800"
              fillOpacity={0.6}
            />
          </AreaChart>
        </ResponsiveContainer>
      </Paper>
    );
  };

  const renderAnalystsTab = () => (
    <Box>
      {renderTrendsChart()}
      <Grid container spacing={3}>
        <Grid item xs={12} md={8}>
          <Typography variant="h6" gutterBottom>
            Top Analyst Opinions
          </Typography>
          {analystsLoading ? (
            renderLoadingState()
          ) : (
            <List>
              {analystsData?.analysts?.map((analyst) => (
                <div key={analyst.id}>
                  <ListItem alignItems="flex-start">
                    <ListItemAvatar>
                      <Avatar>
                        <Star />
                      </Avatar>
                    </ListItemAvatar>
                    <ListItemText
                      primary={analyst.name}
                      secondary={
                        <Box>
                          <Typography variant="body2" component="div">
                            {analyst.firm} • Rating: {analyst.rating}/5
                          </Typography>
                          <Typography
                            variant="body2"
                            color="textSecondary"
                            paragraph
                          >
                            {analyst.latestOpinion}
                          </Typography>
                          <Chip
                            label={analyst.outlook}
                            size="small"
                            color={
                              analyst.outlook === "bullish"
                                ? "success"
                                : analyst.outlook === "bearish"
                                  ? "error"
                                  : "warning"
                            }
                          />
                        </Box>
                      }
                    />
                  </ListItem>
                  <Divider variant="inset" component="li" />
                </div>
              ))}
            </List>
          )}
        </Grid>
        <Grid item xs={12} md={4}>
          <Card>
            <CardHeader title="Analyst Sentiment Summary" />
            <CardContent>
              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" color="textSecondary">
                  Bullish Sentiment
                </Typography>
                <LinearProgress
                  variant="determinate"
                  value={analystsData?.sentiment?.bullish || 0}
                  color="success"
                  sx={{ height: 8, borderRadius: 4 }}
                />
                <Typography variant="caption">
                  {analystsData?.sentiment?.bullish || 0}%
                </Typography>
              </Box>
              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" color="textSecondary">
                  Bearish Sentiment
                </Typography>
                <LinearProgress
                  variant="determinate"
                  value={analystsData?.sentiment?.bearish || 0}
                  color="error"
                  sx={{ height: 8, borderRadius: 4 }}
                />
                <Typography variant="caption">
                  {analystsData?.sentiment?.bearish || 0}%
                </Typography>
              </Box>
              <Box>
                <Typography variant="body2" color="textSecondary">
                  Neutral Sentiment
                </Typography>
                <LinearProgress
                  variant="determinate"
                  value={analystsData?.sentiment?.neutral || 0}
                  color="warning"
                  sx={{ height: 8, borderRadius: 4 }}
                />
                <Typography variant="caption">
                  {analystsData?.sentiment?.neutral || 0}%
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );

  const renderCommentaryTab = () => (
    <Box>
      <Paper sx={{ p: 2, mb: 3 }}>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} sm={4}>
            <FormControl fullWidth size="small">
              <InputLabel>Category</InputLabel>
              <Select
                value={selectedCategory}
                onChange={handleCategoryChange}
                label="Category"
              >
                <MenuItem value="all">All Categories</MenuItem>
                <MenuItem value="stocks">Stocks</MenuItem>
                <MenuItem value="bonds">Bonds</MenuItem>
                <MenuItem value="commodities">Commodities</MenuItem>
                <MenuItem value="crypto">Cryptocurrency</MenuItem>
                <MenuItem value="forex">Forex</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={4}>
            <FormControl fullWidth size="small">
              <InputLabel>Time Period</InputLabel>
              <Select
                value={timePeriod}
                onChange={handleTimePeriodChange}
                label="Time Period"
              >
                <MenuItem value="day">Today</MenuItem>
                <MenuItem value="week">This Week</MenuItem>
                <MenuItem value="month">This Month</MenuItem>
                <MenuItem value="quarter">This Quarter</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={4}>
            <Button
              variant="contained"
              color="primary"
              fullWidth
              onClick={handleSubscribe}
              startIcon={<Event />}
            >
              Subscribe to Updates
            </Button>
          </Grid>
        </Grid>
      </Paper>

      {commentaryLoading ? (
        renderLoadingState()
      ) : commentaryError ? (
        renderErrorState()
      ) : (
        <Box>
          {commentaryData?.commentary?.map((commentary) =>
            renderCommentaryCard(commentary)
          )}
        </Box>
      )}
    </Box>
  );

  return (
    <ErrorBoundary>
      <Box sx={{ p: 3 }}>
        <Typography variant="h4" gutterBottom>
          Market Commentary
        </Typography>
        <Typography variant="subtitle1" color="textSecondary" paragraph>
          Expert insights, analysis, and commentary on current market conditions
        </Typography>

        <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 3 }}>
          <Tabs
            value={activeTab}
            onChange={handleTabChange}
            aria-label="market commentary tabs"
          >
            <Tab label="Commentary" />
            <Tab label="Analyst Opinions" />
            <Tab label="Market Trends" />
          </Tabs>
        </Box>

        {activeTab === 0 && renderCommentaryTab()}
        {activeTab === 1 && renderAnalystsTab()}
        {activeTab === 2 && (
          <Box>
            {renderTrendsChart()}
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <Card>
                  <CardHeader title="Key Market Indicators" />
                  <CardContent>
                    <Box
                      sx={{ display: "flex", flexDirection: "column", gap: 2 }}
                    >
                      {trendsData?.indicators?.map((indicator) => (
                        <Box
                          key={indicator.name}
                          sx={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                          }}
                        >
                          <Typography variant="body2">
                            {indicator.name}
                          </Typography>
                          <Box
                            sx={{
                              display: "flex",
                              alignItems: "center",
                              gap: 1,
                            }}
                          >
                            <Typography variant="body2" fontWeight="medium">
                              {indicator.value}
                            </Typography>
                            <Chip
                              size="small"
                              label={`${indicator.change > 0 ? "+" : ""}${indicator.change}%`}
                              color={
                                indicator.change > 0
                                  ? "success"
                                  : indicator.change < 0
                                    ? "error"
                                    : "default"
                              }
                              icon={
                                indicator.change > 0 ? (
                                  <TrendingUp />
                                ) : indicator.change < 0 ? (
                                  <TrendingDown />
                                ) : null
                              }
                            />
                          </Box>
                        </Box>
                      ))}
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} md={6}>
                <Card>
                  <CardHeader title="Weekly Market Summary" />
                  <CardContent>
                    <Typography variant="body2" paragraph>
                      {trendsData?.weeklyySummary ||
                        "Market trends analysis will be available here with detailed insights into weekly performance, key movements, and outlook for the coming period."}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </Box>
        )}
      </Box>
    </ErrorBoundary>
  );
};

export default MarketCommentary;
