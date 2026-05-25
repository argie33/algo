import { useState, useEffect, useRef } from "react";

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
    if (!open) return;

    const timer = setInterval(() => {
      if (!isMountedRef.current) {
        clearInterval(timer);
        return;
      }

      setCountdown((prev) => {
        const newTime = prev - 1000;
        if (newTime <= 0) {
          clearInterval(timer);
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
  }, [open, onLogout]);

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
    const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000));
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes}:${seconds.toString().padStart(2, "0")}`;
  };

  const progressValue = ((timeRemaining - countdown) / timeRemaining) * 100;

  if (!open) return null;

  return (
    <div style={{
      position: "fixed",
      inset: 0,
      background: "var(--overlay)",
      backdropFilter: "blur(8px)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      zIndex: 999,
    }}>
      <div style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: "var(--r-lg)",
        overflow: "hidden",
        maxWidth: "420px",
        width: "100%",
        boxShadow: "var(--shadow-lg)",
        animation: "slide-up 150ms cubic-bezier(0.4, 0, 0.2, 1)",
      }}>
        {/* Header */}
        <div style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--space-3)",
          padding: "var(--space-4) var(--space-5)",
          borderBottom: "1px solid var(--border)",
          background: "var(--amber-soft)",
        }}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--amber)" strokeWidth="2" strokeLinecap="round">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3.05h16.94a2 2 0 0 0 1.71-3.05L13.71 3.86a2 2 0 0 0-3.42 0z"/>
            <line x1="12" y1="9" x2="12" y2="13"/>
            <line x1="12" y1="17" x2="12.01" y2="17"/>
          </svg>
          <div style={{ fontSize: "var(--t-md)", fontWeight: "var(--w-semibold)", color: "var(--text)" }}>
            Session Expiring Soon
          </div>
        </div>

        {/* Content */}
        <div style={{ padding: "var(--space-5)" }}>
          <div className="alert alert-warn" style={{ marginBottom: "var(--space-4)" }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3.05h16.94a2 2 0 0 0 1.71-3.05L13.71 3.86a2 2 0 0 0-3.42 0z"/>
              <line x1="12" y1="9" x2="12" y2="13"/>
              <line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
            <span style={{ fontSize: "var(--t-sm)" }}>
              Your session will expire in <strong>{formatTime(countdown)}</strong>
            </span>
          </div>

          <div style={{ marginBottom: "var(--space-4)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", marginBottom: "var(--space-2)" }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="2" strokeLinecap="round">
                <circle cx="12" cy="12" r="10"/>
                <polyline points="12 6 12 12 16 14"/>
              </svg>
              <span style={{ fontSize: "var(--t-sm)", color: "var(--text-muted)" }}>Time Remaining</span>
            </div>
            <div style={{
              height: "6px",
              background: "var(--surface-3)",
              borderRadius: "var(--r-pill)",
              overflow: "hidden",
            }}>
              <div style={{
                height: "100%",
                background: countdown < 60000 ? "var(--danger)" : "var(--amber)",
                width: `${100 - progressValue}%`,
                transition: "width 300ms linear",
              }} />
            </div>
          </div>

          <p style={{
            fontSize: "var(--t-sm)",
            color: "var(--text-muted)",
            margin: 0,
            lineHeight: "var(--lh-snug)",
          }}>
            You will be automatically logged out when the timer reaches zero.
            Click "Stay Signed In" to extend your session.
          </p>
        </div>

        {/* Actions */}
        <div style={{
          display: "flex",
          gap: "var(--space-2)",
          padding: "var(--space-4) var(--space-5)",
          borderTop: "1px solid var(--border)",
        }}>
          <button
            onClick={onLogout}
            className="btn btn-outline"
            disabled={extending}
            style={{ flex: 1, justifyContent: "center" }}
          >
            Sign Out Now
          </button>

          <button
            onClick={handleExtend}
            className="btn btn-primary"
            disabled={extending}
            style={{ flex: 1, justifyContent: "center" }}
          >
            {extending ? "Extending…" : "Stay Signed In"}
          </button>
        </div>
      </div>
    </div>
  );
};

export default SessionWarningDialog;