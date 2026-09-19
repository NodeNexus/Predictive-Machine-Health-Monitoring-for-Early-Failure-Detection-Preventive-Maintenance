import type { HealthStatus } from "../../types";
import { StatusBadge } from "./StatusBadge";

interface Props {
  score: number | null | undefined;
  status: HealthStatus;
}

const radius = 43;
const circumference = 2 * Math.PI * radius;

/** Instrument-style score ring. The numeric score and health state come directly from the backend. */
export function HealthGauge({ score, status }: Props) {
  const hasScore = typeof score === "number" && Number.isFinite(score);
  const ringScore = hasScore ? Math.max(0, Math.min(100, score)) : 0;
  const dashOffset = circumference * (1 - ringScore / 100);

  return (
    <div className={`health-gauge health-gauge--${status}`}>
      <svg className="health-gauge__svg" viewBox="0 0 112 112" role="img" aria-label={hasScore ? `Backend health score ${score} out of 100` : "Health score unavailable"}>
        <circle className="health-gauge__track" cx="56" cy="56" r={radius} />
        {hasScore ? <circle className="health-gauge__value-ring" cx="56" cy="56" r={radius} strokeDasharray={circumference} strokeDashoffset={dashOffset} /> : null}
      </svg>
      <div className="health-gauge__readout">
        <strong>{hasScore ? score.toFixed(1) : "—"}</strong>
        <span>{hasScore ? "/ 100" : "NO SCORE"}</span>
      </div>
      <StatusBadge status={status} label={status.toUpperCase()} />
    </div>
  );
}
