import React from "react";
import { Box, CircularProgress, Typography } from "@mui/material";

export const LoadingDisplay = ({ message = "Loading..." }) => {
  return (
    <Box
      display="flex"
      flexDirection="column"
      alignItems="center"
      justifyContent="center"
      minHeight="200px"
      gap={2}
    >
      <CircularProgress size={40} />
      <Typography variant="body1" color="textSecondary">
        {message}
      </Typography>
    </Box>
  );
};

export default LoadingDisplay;
