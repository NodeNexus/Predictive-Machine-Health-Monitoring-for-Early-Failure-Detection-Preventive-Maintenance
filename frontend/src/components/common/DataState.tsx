import type { ReactNode } from "react";

export type DataStateTone = "loading" | "empty" | "error" | "unavailable" | "info";

interface DataStateProps {
  tone?: DataStateTone;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
  compact?: boolean;
  surface?: "dark" | "light";
}

const labels: Record<DataStateTone, string> = {
  loading: "Loading",
  empty: "No data",
  error: "Error",
  unavailable: "Unavailable",
  info: "Information",
};

/** Compact, explicit fallback for every data-driven surface. */
export function DataState({
  tone = "empty",
  title,
  description,
  action,
  className = "",
  compact = false,
  surface = "dark",
}: DataStateProps) {
  const liveRole = tone === "error" ? "alert" : tone === "loading" ? "status" : undefined;

  return (
    <div
      className={`data-state data-state--${tone} data-state--${surface} ${compact ? "data-state--compact" : ""} ${className}`}
      role={liveRole}
      aria-label={`${labels[tone]}: ${title}`}
    >
      <span aria-hidden="true" className="data-state__marker" />
      <div className="data-state__copy">
        <p className="data-state__title">{title}</p>
        {description ? <p className="data-state__description">{description}</p> : null}
        {action ? <div className="data-state__action">{action}</div> : null}
      </div>
    </div>
  );
}
