import type { ReactNode } from "react";

export type MetricValueTone = "default" | "healthy" | "warning" | "critical" | "muted";

interface MetricValueProps {
  label: string;
  value: number | string | null | undefined;
  unit?: ReactNode;
  hint?: ReactNode;
  format?: (value: number) => string;
  tone?: MetricValueTone;
  className?: string;
  valueClassName?: string;
}

function isFiniteNumber(value: number | string | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/** A compact measurement display; null and unavailable remain visibly distinct from zero. */
export function MetricValue({
  label,
  value,
  unit,
  hint,
  format,
  tone = "default",
  className = "",
  valueClassName = "",
}: MetricValueProps) {
  const hasValue = value !== null && value !== undefined && value !== "";
  const formatted = isFiniteNumber(value)
    ? (format ? format(value) : value.toLocaleString())
    : hasValue
      ? String(value)
      : "—";

  return (
    <div className={`metric-value metric-value--${tone} ${className}`}>
      <p className="metric-value__label">{label}</p>
      <p className={`metric-value__value ${valueClassName}`}>
        <span>{formatted}</span>
        {unit && hasValue ? <span className="metric-value__unit">{unit}</span> : null}
      </p>
      {!hasValue ? <span className="sr-only">Value unavailable</span> : null}
      {hint ? <p className="metric-value__hint">{hint}</p> : null}
    </div>
  );
}
