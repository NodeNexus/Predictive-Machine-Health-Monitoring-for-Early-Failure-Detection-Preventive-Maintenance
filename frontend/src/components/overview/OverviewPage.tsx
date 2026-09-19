import type {
  DatasetInfo,
  DemoStartRequest,
  DemoStatus,
  HealthHistoryPoint,
  Machine,
  MachineHealthState,
  MachineVideoEntry,
  TelemetryPayload,
} from "../../types";
import { HealthGauge } from "../common/HealthGauge";
import { Icon } from "../common/Icon";
import { Panel } from "../common/Panel";
import { StatusBadge } from "../common/StatusBadge";
import { HealthTrendChart } from "../charts/TelemetryCharts";
import { DataSourcePanel } from "./DataSourcePanel";
import { ThermalVideoFeed } from "../thermal/ThermalVideoFeed";
import type { AppSection } from "../layout/AppShell";

interface Props {
  machine: Machine | null;
  health: MachineHealthState | null;
  latest: TelemetryPayload | null;
  history: HealthHistoryPoint[];
  datasets: DatasetInfo[];
  machineVideos: MachineVideoEntry[];
  lastMessageAt: number | null;
  demoStatus: DemoStatus | null;
  demoStatusState: "idle" | "loading" | "ready" | "error";
  demoError: string | null;
  demoActionPending: boolean;
  onStartDemo: (request: DemoStartRequest) => Promise<void>;
  onStopDemo: () => Promise<void>;
  onNavigate: (section: AppSection) => void;
}

const modalityMeta = [
  { id: "thermal", label: "Thermal", icon: "thermometer" as const },
  { id: "vibration", label: "Vibration", icon: "activity" as const },
  { id: "acoustic", label: "Acoustic", icon: "wave" as const },
] as const;

function stateMessage(status: string) {
  if (status === "normal") return "Backend reports normal";
  if (status === "warning") return "Backend reports warning";
  if (status === "critical") return "Backend reports critical";
  return "Insufficient evidence for a health state";
}

function clockLabel(timestamp: string | number) {
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime()) ? "Time unavailable" : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function OverviewPage({
  machine,
  health,
  latest,
  history,
  datasets,
  machineVideos,
  lastMessageAt,
  demoStatus,
  demoStatusState,
  demoError,
  demoActionPending,
  onStartDemo,
  onStopDemo,
  onNavigate,
}: Props) {
  const status = health?.status ?? "unknown";
  const confidence = typeof health?.confidence === "number" ? health.confidence : null;
  const mlFusion = latest?.ml_fusion ?? null;
  const mlFusionBadgeStatus = !mlFusion ? "unknown" : mlFusion.reliability === "high" ? "normal" : mlFusion.reliability === "partial" ? "warning" : "unknown";
  const mlFusionBadgeLabel = !mlFusion ? "Awaiting envelope" : mlFusion.reliability === "high" ? "All modalities" : mlFusion.reliability === "partial" ? "Partial coverage" : "Unavailable";
  const runtimeMode = latest?.mode === "demo" ? "Dataset telemetry"
    : latest?.mode === "live" ? "Live telemetry"
      : demoStatus?.running ? "Session running · awaiting envelope"
        : "No active session";
  const metadata = machine ? [machine.machine_type, machine.model, machine.location].filter((value): value is string => Boolean(value?.trim())) : [];
  const activeThermalPath = demoStatus?.sources?.thermal ?? null;
  const activeVideo = activeThermalPath ? machineVideos.find((entry) => entry.path === activeThermalPath) ?? null : null;

  return (
    <div className="page page-overview">
      <div className="console-heading">
        <div className="console-heading__identity">
          <p className="section-heading__eyebrow">Fusion / multimodal monitoring</p>
          <h1>{machine?.machine_name ?? "No machine selected"}</h1>
          <div className="console-heading__meta">
            {machine ? <code>{machine.machine_id}</code> : <span>Register an asset to begin monitoring.</span>}
            {metadata.map((value) => <span key={value}>{value}</span>)}
          </div>
        </div>
        <div className="console-heading__state">
          <StatusBadge status={status} label={status.toUpperCase()} />
          <span className="console-heading__mode">{runtimeMode}</span>
          <span className="console-heading__updated">{lastMessageAt ? `Envelope ${clockLabel(lastMessageAt)}` : "No envelope received"}</span>
          {!machine ? <button type="button" className="text-button" onClick={() => onNavigate("machines")}>Open machine registry <Icon name="arrow" size={13} /></button> : null}
        </div>
      </div>

      <div className="fusion-grid">
        <DataSourcePanel
          machine={machine}
          datasets={datasets}
          machineVideos={machineVideos}
          demoStatus={demoStatus}
          demoStatusState={demoStatusState === "idle" ? "loading" : demoStatusState}
          demoError={demoError}
          actionPending={demoActionPending}
          onStart={onStartDemo}
          onStop={onStopDemo}
          onNavigate={onNavigate}
        />

        <ThermalVideoFeed className="sensor-visual-panel" activeVideo={activeVideo} sessionRunning={Boolean(demoStatus?.running)} thermal={latest?.thermal ?? null} />

        <Panel tone="ink" className="machine-health-panel">
          <div className="panel-title-row">
            <div><div className="panel-kicker">Machine health</div><h2>Fusion output</h2></div>
            <StatusBadge status={status} label={status.toUpperCase()} />
          </div>
          <div className="machine-health-panel__body">
            <HealthGauge score={health?.health_score} status={status} />
            <div className="machine-health-panel__readouts">
              <div><span>Confidence / coverage</span><strong>{confidence === null ? "Not reported" : `${Math.round(confidence * 100)}%`}</strong></div>
            </div>
          </div>
          <p className="machine-health-panel__note">{stateMessage(status)}. Confidence describes calibrated modality coverage, not probability.</p>
        </Panel>

        <Panel tone="ink" className="health-trend-panel">
          <HealthTrendChart points={history} title="Health history" description="Backend score samples from REST history and accepted envelopes." source="REST + WebSocket" height={155} className="health-trend-chart" />
        </Panel>

        <Panel tone="amber" className="ml-fusion-panel">
          <div className="panel-title-row">
            <div><div className="panel-kicker">Supplementary evidence · not machine health</div><h2>Multimodal ML Evidence (V1)</h2></div>
            <StatusBadge status={mlFusionBadgeStatus} label={mlFusionBadgeLabel} />
          </div>
          <div className="contribution-list">
            {modalityMeta.map((modality) => {
              const evidence = mlFusion?.modality_evidence[modality.id];
              const reliabilityLabel = !evidence?.available ? "n/a" : evidence.reliability === "high" ? "High" : evidence.reliability === "low" ? "Suppressed" : "Unavailable";
              const badgeStatus = evidence?.reliability === "high" ? "normal" : evidence?.reliability === "low" ? "warning" : "unknown";
              const strengthLabel = evidence?.anomaly_strength != null ? evidence.anomaly_strength.toFixed(2) : "—";
              return (
                <div className="contribution-row" key={modality.id}>
                  <div className="contribution-row__head">
                    <span className={`modality-dot modality-dot--${modality.id}`} />
                    <span>{modality.label}</span>
                    <StatusBadge status={badgeStatus} label={reliabilityLabel} size="sm" />
                    <strong>{strengthLabel}</strong>
                  </div>
                </div>
              );
            })}
          </div>
          <div className="machine-health-panel__readouts">
            <div><span>Fused evidence</span><strong>{mlFusion?.fused_severity != null ? mlFusion.fused_severity.toFixed(2) : "Unavailable"}</strong></div>
            <div><span>Confidence</span><strong>{mlFusion ? mlFusion.fused_confidence.toFixed(2) : "—"}</strong></div>
          </div>
          <p className="chart-note">
            Supplementary ML evidence only — this is NOT the deterministic machine health above, and
            <code> fused_severity</code> is a confidence-weighted average of heterogeneous per-modality
            readings, not a calibrated failure probability. A suppressed or missing modality contributes
            zero weight and is never treated as normal.
          </p>
        </Panel>
      </div>
    </div>
  );
}
