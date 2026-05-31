import React from "react";
import { useNavigate } from "react-router-dom";

export default function NotFound() {
  const navigate = useNavigate();
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: "60vh", gap: "1rem" }}>
      <h1 style={{ margin: 0, fontSize: "3rem", color: "var(--text)" }}>404</h1>
      <h2 style={{ margin: 0, fontSize: "1.5rem", color: "var(--text-muted)" }}>Page not found</h2>
      <button className="btn btn-primary" onClick={() => navigate("/app")}>Go to Dashboard</button>
    </div>
  );
}

