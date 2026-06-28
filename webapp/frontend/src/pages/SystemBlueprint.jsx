import React from "react";
import { Box, Typography } from "@mui/material";

export default function SystemBlueprint() {
  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        height: "calc(100vh - 64px)",
      }}
    >
      <Box
        sx={{ px: 2, py: 1, borderBottom: "1px solid", borderColor: "divider" }}
      >
        <Typography variant="subtitle2" color="text.secondary">
          Algo Trading System — Complete Solution Blueprint
        </Typography>
      </Box>
      <Box sx={{ flex: 1, overflow: "hidden" }}>
        <iframe
          src="/solution-blueprint.html"
          title="Solution Blueprint"
          style={{ width: "100%", height: "100%", border: "none" }}
        />
      </Box>
    </Box>
  );
}
