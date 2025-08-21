import { Container, Typography, Paper, Button } from "@mui/material";
import { Construction } from "@mui/icons-material";
import { useNavigate } from "react-router-dom";

function ComingSoon({
  pageName = "This Page",
  description = "This feature is currently under development.",
}) {
  const navigate = useNavigate();

  return (
    <Container maxWidth="md" sx={{ py: 8 }}>
      <Paper
        elevation={0}
        sx={{
          p: 6,
          textAlign: "center",
          backgroundColor: "background.default",
        }}
      >
        <Construction sx={{ fontSize: 80, color: "primary.main", mb: 3 }} />

        <Typography variant="h3" gutterBottom color="primary">
          {pageName} Coming Soon
        </Typography>

        <Typography variant="h6" color="text.secondary" sx={{ mb: 4 }}>
          {description}
        </Typography>

        <Typography variant="body1" color="text.secondary" sx={{ mb: 4 }}>
          We&apos;re working hard to bring you this feature. Please check back
          later!
        </Typography>

        <Button variant="contained" onClick={() => navigate("/")} size="large">
          Return to Dashboard
        </Button>
      </Paper>
    </Container>
  );
}

export default ComingSoon;
