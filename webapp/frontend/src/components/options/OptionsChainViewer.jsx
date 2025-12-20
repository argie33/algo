import React, { useState } from "react";
import {
  Box,
  TextField,
  Button,
  Alert,
  Typography,
  Paper,
} from "@mui/material";

function OptionsChainViewer() {
  const [symbol, setSymbol] = useState("");

  return (
    <Box>
      <Paper sx={{ p: 2, mb: 3 }}>
        <Typography variant="h6" sx={{ mb: 2 }}>
          Options Chain Explorer
        </Typography>
        <Box sx={{ display: "flex", gap: 2, mb: 2 }}>
          <TextField
            label="Symbol"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            placeholder="e.g., AAPL"
            size="small"
          />
          <Button variant="contained" disabled>
            View Chain
          </Button>
        </Box>
        <Alert severity="info">
          This feature allows you to view the complete options chain (all calls and puts) for a selected symbol, including all strike prices, expirations, and Greeks data. Coming soon.
        </Alert>
      </Paper>
    </Box>
  );
}

export default OptionsChainViewer;
