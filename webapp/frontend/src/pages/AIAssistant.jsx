import { Box, Typography, Paper, Container } from "@mui/material";
import EnhancedAIChat from "../components/EnhancedAIChat";

const AIAssistant = () => {
  return (
    <Container maxWidth="xl">
      <Box sx={{ py: 3 }}>
        {/* Page Header */}
        <Box sx={{ mb: 3 }}>
          <Typography variant="h4" component="h1" gutterBottom>
            AI Assistant
          </Typography>
          <Typography variant="h6" color="text.secondary" gutterBottom>
            Your personal AI-powered investment assistant powered by Claude
          </Typography>
        </Box>

        {/* Main Chat Interface */}
        <Paper
          sx={{
            p: 0,
            height: "calc(100vh - 280px)",
            minHeight: "600px",
            overflow: "hidden",
            borderRadius: 2,
            boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
          }}
        >
          <EnhancedAIChat />
        </Paper>

        {/* Help Text */}
        <Box sx={{ mt: 2, textAlign: "center" }}>
          <Typography variant="body2" color="text.secondary">
            Ask me anything about your portfolio, market analysis, investment
            strategies, or financial data. I can help with technical analysis,
            market insights, and personalized investment guidance.
          </Typography>
        </Box>
      </Box>
    </Container>
  );
};

export default AIAssistant;
