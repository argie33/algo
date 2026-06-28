import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  Box,
  Typography,
  Button,
  LinearProgress,
} from "@mui/material";
import { Clock } from "@mui/icons-material";

const SessionExpiredModal = ({ open, onClose, countdownSeconds = 10 }) => {
  const [countdown, setCountdown] = useState(countdownSeconds);

  useEffect(() => {
    if (!open) {
      setCountdown(countdownSeconds);
      return;
    }

    const interval = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          window.location.href = "/login";
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [open, countdownSeconds]);

  const progress = ((countdownSeconds - countdown) / countdownSeconds) * 100;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      disableEscapeKeyDown
      maxWidth="sm"
      fullWidth
    >
      <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        <Clock />
        Session Expired
      </DialogTitle>
      <DialogContent>
        <Box sx={{ pt: 2, textAlign: "center" }}>
          <Typography variant="body1" sx={{ mb: 2 }}>
            Your session has expired. You will be redirected to login in{" "}
            <strong>
              {countdown} second{countdown !== 1 ? "s" : ""}
            </strong>
            .
          </Typography>
          <LinearProgress
            variant="determinate"
            value={progress}
            sx={{ mb: 2 }}
          />
          <Typography
            variant="caption"
            color="textSecondary"
            sx={{ mb: 3, display: "block" }}
          >
            Click below to return to login immediately.
          </Typography>
          <Button
            variant="contained"
            onClick={() => {
              window.location.href = "/login";
            }}
            fullWidth
          >
            Go to Login Now
          </Button>
        </Box>
      </DialogContent>
    </Dialog>
  );
};

export default SessionExpiredModal;
