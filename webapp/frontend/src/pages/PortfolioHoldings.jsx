// This file has been superseded by PortfolioDashboard.jsx
// Keeping it for backward compatibility, but redirecting to the new dashboard

import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Box, CircularProgress } from "@mui/material";

export default function PortfolioHoldings() {
  const navigate = useNavigate();

  useEffect(() => {
    // Redirect to the new portfolio dashboard
    navigate("/portfolio", { replace: true });
  }, [navigate]);

  return (
    <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
      <CircularProgress />
    </Box>
  );
}
