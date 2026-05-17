import React from "react";
import { Box, Typography, Button } from "@mui/material";
import { useNavigate } from "react-router-dom";

export default function NotFound() {
  const navigate = useNavigate();
  return (
    <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: "60vh", gap: 2 }}>
      <Typography variant="h3" color="text.secondary">404</Typography>
      <Typography variant="h6" color="text.secondary">Page not found</Typography>
      <Button variant="contained" onClick={() => navigate("/app")}>Go to Dashboard</Button>
    </Box>
  );
}
