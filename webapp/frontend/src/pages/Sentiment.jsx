import React from "react";
import {
  Container,
  Typography,
  Box,
  Card,
  CardContent,
  Alert,
} from "@mui/material";
import { TrendingUp } from "@mui/icons-material";

function Sentiment() {
  return (
    <Container maxWidth="xl" sx={{ py: 3 }}>
      <Box sx={{ mb: 3 }}>
        <Box display="flex" alignItems="center" gap={2}>
          <TrendingUp sx={{ fontSize: 40, color: "primary.main" }} />
          <Typography variant="h4" component="h1">
            Stock Sentiment Analysis
          </Typography>
        </Box>
        <Typography variant="subtitle1" color="textSecondary" sx={{ mt: 1 }}>
          Analyze market sentiment indicators for individual stocks
        </Typography>
      </Box>

      <Alert severity="info" sx={{ mb: 3 }}>
        Stock sentiment features coming soon. For market-level sentiment indicators, please visit the Markets page.
      </Alert>

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Available Features
          </Typography>
          <Typography variant="body2" color="textSecondary">
            • Stock-specific sentiment scores
            <br />
            • Social media mentions and trends
            <br />
            • News sentiment analysis
            <br />
            • Analyst ratings and recommendations
          </Typography>
        </CardContent>
      </Card>
    </Container>
  );
}

export default Sentiment;
