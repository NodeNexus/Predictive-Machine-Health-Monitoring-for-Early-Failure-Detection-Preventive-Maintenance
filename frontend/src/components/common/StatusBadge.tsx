export type StatusBadgeStatus =
  | "normal"
  | "healthy"
  | "warning"
  | "critical"
  | "unknown"
  | "calibrating"
  | "insufficient_baseline"
  | "missing_data"
  | "modality_unavailable"
  | "connected"
  | "connecting"
  | "reconnecting"
  | "awaiting"
  | "stale"
  | "disconnected"
  | "not_connected"
  | "backend_unavailable"
  | "websocket_disconnected"
  | "loading"
  | "empty"
  | "offline"
  | "demo"
  | "live"
  | "error";

/** Status vocabulary used by the application shell and telemetry surfaces. */
export type SurfaceStatus =
  | "connected"
  | "connecting"
  | "reconnecting"
  | "awaiting"
  | "stale"
  | "disconnected"
  | "offline"
  | "error"
  | "demo"
  | "live"
  | "insufficient"
  | "not_connected";

interface StatusBadgeProps {
  status: StatusBadgeStatus | string;
  label?: string;
  size?: "sm" | "md";
  className?: string;
}

const labels: Record<string, string> = {
  normal: "Normal",
  healthy: "Healthy",
  warning: "Warning",
  critical: "Critical",
  unknown: "Unknown",
  calibrating: "Calibrating",
  insufficient_baseline: "Insufficient baseline",
  missing_data: "Missing data",
  modality_unavailable: "Modality unavailable",
  connected: "Connected",
  connecting: "Connecting",
  reconnecting: "Reconnecting",
  awaiting: "Awaiting telemetry",
  stale: "Stale",
  disconnected: "Disconnected",
  not_connected: "Not connected",
  backend_unavailable: "Backend unavailable",
  websocket_disconnected: "WebSocket disconnected",
  loading: "Loading",
  empty: "No data",
  offline: "Offline",
  demo: "Dataset demo",
  live: "Live source",
  error: "Error",
  insufficient: "Insufficient evidence",
};

function normalize(status: string) {
  if (status === "healthy") return "normal";
  if (status === "insufficient_baseline") return "insufficient";
  if (status === "websocket_disconnected" || status === "backend_unavailable") return "error";
  if (status === "missing_data" || status === "modality_unavailable") return "unavailable";
  if (status === "not_connected") return "disconnected";
  return status;
}

/** Status always includes a textual label; color is never the only signal. */
export function StatusBadge({ status, label, size = "sm", className = "" }: StatusBadgeProps) {
  const normalized = normalize(status);
  const readable = labels[status] ?? status.replace(/[_-]+/g, " ").replace(/\b\w/g, (character) => character.toUpperCase());

  return (
    <span className={`status-badge status-badge--${normalized} ${size === "md" ? "status-badge--md" : ""} ${className}`}>
      <span aria-hidden="true" className="status-badge__dot" />
      <span>{label ?? readable}</span>
    </span>
  );
}
