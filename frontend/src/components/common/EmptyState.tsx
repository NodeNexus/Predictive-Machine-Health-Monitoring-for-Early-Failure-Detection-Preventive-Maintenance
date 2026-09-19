import type { ReactNode } from "react";
import { Icon, type IconName } from "./Icon";

interface Props {
  icon?: IconName;
  title: string;
  description: string;
  action?: ReactNode;
  compact?: boolean;
}

export function EmptyState({ icon = "database", title, description, action, compact = false }: Props) {
  return (
    <div className={"empty-state " + (compact ? "empty-state--compact" : "")}>
      <div className="empty-state__icon">
        <Icon name={icon} size={compact ? 16 : 20} />
      </div>
      <div>
        <h3>{title}</h3>
        <p>{description}</p>
        {action && <div className="empty-state__action">{action}</div>}
      </div>
    </div>
  );
}

export function LoadingState({ label = "Loading system data…" }: { label?: string }) {
  return (
    <div className="loading-state" role="status" aria-live="polite">
      <span className="loading-state__bar" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}
