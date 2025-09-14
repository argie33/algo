import { useState, useEffect, useRef } from "react";
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Typography,
  Box,
  LinearProgress,
  Alert,
  CircularProgress,
} from "@mui/material";
import { Warning, AccessTime } from "@mui/icons-material";

const SessionWarningDialog = ({
  open,
  timeRemaining,
  onExtend,
  onLogout,
  onClose,
}) => {
  const [countdown, setCountdown] = useState(timeRemaining);
  const [extending, setExtending] = useState(false);
  const isMountedRef = useRef(true);

  useEffect(() => {
    setCountdown(timeRemaining);
  }, [timeRemaining]);

  useEffect(() => {
    if (!open || countdown <= 0) return;

    const timer = setInterval(() => {
      if (!isMountedRef.current) {
        clearInterval(timer);
        return;
      }

      setCountdown((prev) => {
        const newTime = prev - 1000;
        if (newTime <= 0) {
          // Clear timer before calling onLogout to prevent further updates
          clearInterval(timer);
          // Auto logout when time expires
          if (isMountedRef.current) {
            onLogout();
          }
          return 0;
        }
        return newTime;
      });
    }, 1000);

    return () => {
      clearInterval(timer);
    };
  }, [open, countdown, onLogout]);

  useEffect(() => {
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const handleExtend = async () => {
    setExtending(true);
    try {
      await onExtend();
      onClose();
    } catch (error) {
      console.error("Failed to extend session:", error);
    } finally {
      setExtending(false);
    }
  };

  const formatTime = (milliseconds) => {
    const totalSeconds = Math.floor(milliseconds / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes}:${seconds.toString().padStart(2, "0")}`;
  };

  const progressValue = ((timeRemaining - countdown) / timeRemaining) * 100;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="sm"
      fullWidth
      disableEscapeKeyDown
      PaperProps={{
        sx: {
          borderRadius: 2,
          border: "2px solid",
          borderColor: "warning.main",
        },
      }}
    >
      <DialogTitle>
        <Box display="flex" alignItems="center" gap={1}>
          <Warning color="warning" />
          <Typography variant="h6">Session Expiring Soon</Typography>
        </Box>
      </DialogTitle>

      <DialogContent>
        <Alert severity="warning" sx={{ mb: 2 }}>
          Your session will expire in <strong>{formatTime(countdown)}</strong>
        </Alert>

        <Box sx={{ mb: 2 }}>
          <Box display="flex" alignItems="center" gap={1} mb={1}>
            <AccessTime fontSize="small" />
            <Typography variant="body2" color="text.secondary">
              Time Remaining
            </Typography>
          </Box>
          <LinearProgress
            variant="determinate"
            value={100 - progressValue}
            color={countdown < 60000 ? "error" : "warning"}
            sx={{ height: 8, borderRadius: 4 }}
          />
        </Box>

        <Typography variant="body2" color="text.secondary">
          You will be automatically logged out when the timer reaches zero.
          Click &quot;Stay Signed In&quot; to extend your session.
        </Typography>
      </DialogContent>

      <DialogActions sx={{ p: 2, gap: 1 }}>
        <Button
          onClick={onLogout}
          color="error"
          variant="outlined"
          disabled={extending}
        >
          Sign Out Now
        </Button>

        <Button
          onClick={handleExtend}
          color="primary"
          variant="contained"
          disabled={extending}
          startIcon={extending ? <CircularProgress size={16} /> : null}
        >
          {extending ? "Extending..." : "Stay Signed In"}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default SessionWarningDialog;
