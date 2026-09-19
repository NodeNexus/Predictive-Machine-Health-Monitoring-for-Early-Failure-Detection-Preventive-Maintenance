import type { AnomalyEventRecord } from "../../types";
import { DataState } from "../common/DataState";
import { Icon } from "../common/Icon";
import { Panel } from "../common/Panel";
import { SectionHeading } from "../common/SectionHeading";
import { StatusBadge } from "../common/StatusBadge";

interface Props {
  events: AnomalyEventRecord[];
  machineName?: string;
  loading?: boolean;
  error?: string | null;
  onRefresh?: () => void;
}

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Time unavailable" : date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function evidenceCount(event: AnomalyEventRecord) {
  const list = event.evidence?.evidence;
  return Array.isArray(list) ? list.length : 0;
}

export function EventsPage({ events, machineName, loading = false, error = null, onRefresh }: Props) {
  return (
    <div className="page">
      <SectionHeading
        eyebrow="Confirmed signals"
        title="Events"
        description={machineName ? "Persisted anomaly transitions for " + machineName + ". Events appear only after the backend's temporal persistence rules are met." : "Persisted anomaly transitions from the selected machine."}
        action={<button type="button" className="button button-secondary" onClick={onRefresh} disabled={!onRefresh || loading}><Icon name="arrow" size={14} /> Refresh</button>}
      />
      <Panel tone="paper" className="events-table-panel">
        <div className="panel-title-row">
          <div><div className="panel-kicker panel-kicker--dark">Event ledger</div><h3>{events.length} recorded transition{events.length === 1 ? "" : "s"}</h3></div>
          <span className="panel-title-row__hint">Newest first from the backend</span>
        </div>
        {loading ? <DataState tone="loading" title="Loading event ledger" description="Reading persisted anomaly transitions." surface="light" /> : null}
        {!loading && error ? <DataState tone="error" title="Events unavailable" description={error} surface="light" /> : null}
        {!loading && !error && events.length === 0 ? <DataState tone="empty" title="No confirmed events" description="A single abnormal frame is not an event. The backend persists a transition after its temporal thresholds are met." surface="light" /> : null}
        <div className="event-ledger" role="list">
          {events.map((event) => {
            const open = event.resolved_at === null;
            const severity = event.severity === "high" ? "critical" : event.severity === "moderate" ? "warning" : "unknown";
            return (
              <article className="event-ledger__row" key={event.event_id} role="listitem">
                <div className={"event-ledger__severity event-ledger__severity--" + severity} aria-hidden="true" />
                <div className="event-ledger__main">
                  <div className="event-ledger__title"><strong>{event.severity} severity anomaly</strong><StatusBadge status={open ? "critical" : "normal"} label={open ? "Open" : "Resolved"} /></div>
                  <p>{formatDate(event.started_at)}{event.resolved_at ? " → " + formatDate(event.resolved_at) : " · still open"}</p>
                </div>
                <div className="event-ledger__meta">
                  <span>Contributors</span>
                  <strong>{Object.keys(event.modality_contributions ?? {}).length || "—"}</strong>
                </div>
                <div className="event-ledger__meta">
                  <span>Evidence items</span>
                  <strong>{evidenceCount(event) || "—"}</strong>
                </div>
                <details className="event-ledger__details">
                  <summary aria-label="Show event evidence"><Icon name="chevron" size={14} /></summary>
                  <div className="event-evidence">
                    {Object.entries(event.modality_contributions ?? {}).map(([modality, contribution]) => <span key={modality}>{modality}: {typeof contribution === "number" ? Math.round(contribution * 100) + "%" : "—"}</span>)}
                    {evidenceCount(event) === 0 ? <span>No evidence details persisted.</span> : null}
                  </div>
                </details>
              </article>
            );
          })}
        </div>
      </Panel>
    </div>
  );
}
