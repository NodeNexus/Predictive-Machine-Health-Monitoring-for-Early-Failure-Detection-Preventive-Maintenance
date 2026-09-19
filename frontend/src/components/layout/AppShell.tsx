import { useState, type ReactNode } from "react";
import type { DemoStatus, Machine, TelemetryMode } from "../../types";
import { Icon, type IconName } from "../common/Icon";
import { StatusBadge, type SurfaceStatus } from "../common/StatusBadge";

export type AppSection = "fusion" | "thermal" | "vibration" | "acoustic" | "events" | "machines" | "datasets" | "devices" | "demo";

interface Props {
  section: AppSection;
  onSectionChange: (section: AppSection) => void;
  machines: Machine[];
  selectedMachineId: string | null;
  onMachineChange: (machineId: string) => void;
  apiStatus: SurfaceStatus;
  telemetryStatus: SurfaceStatus;
  telemetryLabel?: string;
  demoStatus: DemoStatus | null;
  demoStatusState: "loading" | "ready" | "error";
  dataMode: TelemetryMode | null;
  children: ReactNode;
}

const primaryNavigation: Array<{ id: AppSection; label: string; icon: IconName }> = [
  { id: "thermal", label: "Thermal", icon: "thermometer" },
  { id: "vibration", label: "Vibration", icon: "pulse" },
  { id: "acoustic", label: "Acoustic", icon: "wave" },
  { id: "fusion", label: "Fusion", icon: "grid" },
  { id: "events", label: "Events", icon: "bell" },
  { id: "machines", label: "Machines", icon: "machine" },
];

function readableConnection(status: SurfaceStatus, label?: string) {
  if (label) return label;
  if (status === "connected") return "Connected";
  if (status === "awaiting") return "Awaiting data";
  if (status === "connecting") return "Connecting";
  if (status === "reconnecting") return "Reconnecting";
  if (status === "stale") return "Stale data";
  if (status === "error") return "Error";
  return "Disconnected";
}

function LogoMark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <Icon name="settings" size={25} strokeWidth={1.8} />
      <span className="brand-mark__core" />
    </span>
  );
}

export function AppShell({
  section,
  onSectionChange,
  machines,
  selectedMachineId,
  onMachineChange,
  apiStatus,
  telemetryStatus,
  telemetryLabel,
  demoStatus,
  demoStatusState,
  dataMode,
  children,
}: Props) {
  const [assetsOpen, setAssetsOpen] = useState(false);
  const demoLabel = demoStatusState === "loading"
    ? "Checking"
    : demoStatusState === "error"
      ? "Status unavailable"
      : demoStatus?.running
        ? "Session running"
        : "Session idle";

  function openSection(next: AppSection) {
    onSectionChange(next);
    setAssetsOpen(false);
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to monitoring workspace</a>
      <header className="topbar">
        <div className="app-brand" aria-label="IDEA LAB Machine Health Monitoring">
          <LogoMark />
          <span className="app-brand__copy">
            <strong>IDEA LAB</strong>
            <small>MACHINE HEALTH MONITORING</small>
          </span>
        </div>

        <nav className="app-nav" aria-label="Primary navigation">
          {primaryNavigation.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`app-nav__item ${section === item.id ? "is-active" : ""}`}
              onClick={() => openSection(item.id)}
              aria-current={section === item.id ? "page" : undefined}
            >
              <Icon name={item.icon} size={17} />
              <span>{item.label}</span>
            </button>
          ))}
          <details className={`app-nav__assets ${section === "datasets" || section === "devices" ? "is-active" : ""}`} open={assetsOpen}>
            <summary onClick={(event) => { event.preventDefault(); setAssetsOpen((open) => !open); }} aria-expanded={assetsOpen}>
              <Icon name="database" size={16} />
              <span>Data</span>
              <Icon name="chevron" size={13} />
            </summary>
            {assetsOpen ? (
              <div className="app-nav__menu">
                {(["datasets", "devices"] as const).map((item) => (
                  <button key={item} type="button" onClick={() => openSection(item)} aria-current={section === item ? "page" : undefined}>
                    <Icon name={item === "datasets" ? "database" : "radio"} size={15} />
                    {item === "datasets" ? "Datasets" : "Devices"}
                  </button>
                ))}
              </div>
            ) : null}
          </details>
        </nav>

        <div className="topbar__machine">
          <label htmlFor="active-machine">Machine</label>
          <select
            id="active-machine"
            value={selectedMachineId ?? ""}
            onChange={(event) => onMachineChange(event.target.value)}
            disabled={machines.length === 0}
            aria-label="Select active machine"
          >
            {machines.length === 0 ? <option value="">No machines registered</option> : null}
            {machines.map((machine) => <option key={machine.machine_id} value={machine.machine_id}>{machine.machine_name}</option>)}
          </select>
          <Icon name="chevron" size={13} />
        </div>

        <div className="topbar__system" aria-label="System connections">
          <StatusBadge status={apiStatus} label={apiStatus === "connected" ? "API ready" : apiStatus === "connecting" ? "API checking" : "API error"} />
          <StatusBadge status={telemetryStatus} label={`WS ${readableConnection(telemetryStatus, telemetryLabel)}`} />
        </div>

        <button
          type="button"
          className={`demo-mode-control ${demoStatus?.running ? "is-running" : ""} ${demoStatusState === "error" ? "has-error" : ""}`}
          onClick={() => openSection("demo")}
          aria-label={`Open dataset demo controls. ${demoLabel}. Current envelope mode: ${dataMode ?? "not reported"}.`}
        >
          <span className="demo-mode-control__mark"><Icon name="play" size={13} /></span>
          <span className="demo-mode-control__copy"><strong>DATASET DEMO</strong><small>{demoLabel}</small></span>
        </button>
      </header>

      <main className="app-content" id="main-content" tabIndex={-1}>
        {children}
      </main>
    </div>
  );
}
