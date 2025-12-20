import React from "react";
import {
  Box,
  Alert,
  AlertTitle,
  Typography,
} from "@mui/material";
import InfoIcon from "@mui/icons-material/Info";
import CoveredCallOpportunities from "../components/options/CoveredCallOpportunities";

function HedgeHelper() {
  return (
    <Box sx={{ width: "100%" }}>
      {/* Header */}
      <Box sx={{ mb: 3 }}>
        <Typography variant="h4" sx={{ fontWeight: 700, mb: 1 }}>
          Hedge Helper
        </Typography>
        <Typography variant="subtitle1" sx={{ color: "text.secondary" }}>
          Covered call opportunities and recommendations
        </Typography>
      </Box>

      {/* Info Alert */}
      <Alert
        icon={<InfoIcon />}
        severity="info"
        sx={{ mb: 3 }}
      >
        <AlertTitle>Covered Call Strategy</AlertTitle>
        A covered call is an options strategy where you sell call options on stocks you own to generate income from option premiums. This tool identifies optimal times and strike prices to execute this strategy based on technical analysis and options data.
      </Alert>

      {/* Covered Call Opportunities */}
      <CoveredCallOpportunities />
    </Box>
  );
}

export default HedgeHelper;
