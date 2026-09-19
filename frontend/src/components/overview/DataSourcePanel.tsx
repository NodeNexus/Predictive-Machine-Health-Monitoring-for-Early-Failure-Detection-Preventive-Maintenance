import { useMemo, useState } from "react";
import type { DatasetInfo, DemoStartRequest, DemoStatus, Machine, MachineVideoEntry, Modality } from "../../types";
import { Icon } from "../common/Icon";
import { Panel } from "../common/Panel";
import { StatusBadge } from "../common/StatusBadge";
import type { AppSection } from "../layout/AppShell";

interface Props {
  machine: Machine | null;
  datasets: DatasetInfo[];
  machineVideos: MachineVideoEntry[];
  demoStatus: DemoStatus | null;
  demoStatusState: "loading" | "ready" | "error";
  demoError: string | null;
  actionPending: boolean;
  onStart: (request: DemoStartRequest) => Promise<void>;
  onStop: () => Promise<void>;
  onNavigate: (section: AppSection) => void;
}

const modalityLabels: Array<{ key: Modality; label: string; icon: "thermometer" | "activity" | "wave" }> = [
  { key: "thermal", label: "Thermal", icon: "thermometer" },
  { key: "vibration", label: "Vibration", icon: "activity" },
  { key: "acoustic", label: "Acoustic", icon: "wave" },
];

const datasetModalityLabels: Array<{ key: Extract<Modality, "vibration" | "acoustic">; label: string; icon: "activity" | "wave" }> = [
  { key: "vibration", label: "Vibration", icon: "activity" },
  { key: "acoustic", label: "Acoustic", icon: "wave" },
];

export function DataSourcePanel({
  machine,
  datasets,
  machineVideos,
  demoStatus,
  demoStatusState,
  demoError,
  actionPending,
  onStart,
  onStop,
  onNavigate,
}: Props) {
  const [sources, setSources] = useState<Record<Modality, string>>({ thermal: "", vibration: "", acoustic: "" });
  const [actionError, setActionError] = useState<string | null>(null);
  const options = useMemo(() => ({
    vibration: datasets.filter((dataset) => dataset.modality.toLowerCase() === "vibration" && dataset.path.trim()),
    acoustic: datasets.filter((dataset) => dataset.modality.toLowerCase() === "acoustic" && dataset.path.trim()),
  }), [datasets]);
  // One visible entry per machine identity, even when multiple videos map
  // to the same name (e.g. two Honda Engine clips) - the machine list is a
  // list of machines, not a list of video files. The backend registry
  // still keeps every underlying video mapped; this only picks the first
  // (lowest video_id) one to drive the simplified selector.
  const machineOptions = useMemo(() => {
    const seen = new Set<string>();
    const unique: MachineVideoEntry[] = [];
    for (const entry of machineVideos) {
      if (seen.has(entry.name)) continue;
      seen.add(entry.name);
      unique.push(entry);
    }
    return unique;
  }, [machineVideos]);
  const selectedCount = Object.values(sources).filter(Boolean).length;
  const running = Boolean(demoStatus?.running);
  const canStart = Boolean(machine) && demoStatusState === "ready" && !running && !actionPending && selectedCount > 0;

  async function start() {
    if (!machine || !canStart) return;
    setActionError(null);
    try {
      await onStart({
        machine_id: machine.machine_id,
        thermal_source: sources.thermal || null,
        vibration_source: sources.vibration || null,
        acoustic_source: sources.acoustic || null,
        vibration_channel: 0,
        playback_speed: 1,
      });
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Demo session could not be started.");
    }
  }

  async function stop() {
    if (!running || actionPending) return;
    setActionError(null);
    try {
      await onStop();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Demo session could not be stopped.");
    }
  }

  return (
    <Panel tone="ink" className="source-control-panel">
      <div className="panel-title-row source-control-panel__heading">
        <div><div className="panel-kicker">Data source</div><h2>Dataset inputs</h2></div>
        <StatusBadge status={running ? "demo" : demoStatusState === "error" ? "error" : demoStatusState === "loading" ? "loading" : "offline"} label={running ? "Session running" : demoStatusState === "error" ? "Status error" : demoStatusState === "loading" ? "Checking" : "Idle"} />
      </div>

      <div className="source-control-panel__asset">
        <span>Selected machine</span>
        <strong>{machine?.machine_name ?? "No machine selected"}</strong>
        {machine ? <code>{machine.machine_id}</code> : null}
      </div>

      <div className="source-selectors">
        <label className="source-select" key="thermal-machine">
          <span className="source-select__label"><Icon name="thermometer" size={15} />Machine (thermal video)</span>
          <select
            value={sources.thermal}
            onChange={(event) => setSources((current) => ({ ...current, thermal: event.target.value }))}
            disabled={running || machineOptions.length === 0}
            aria-label="Select machine"
          >
            <option value="">{machineOptions.length ? "Select a machine" : "No machines registered"}</option>
            {machineOptions.map((entry) => (
              <option key={entry.machine_video_id} value={entry.path}>{entry.name}</option>
            ))}
          </select>
          <small className="source-select__note">Predefined machine list - the video is selected automatically, never typed.</small>
        </label>
        {datasetModalityLabels.map((modality) => (
          <label className="source-select" key={modality.key}>
            <span className="source-select__label"><Icon name={modality.icon} size={15} />{modality.label} dataset</span>
            <select
              value={sources[modality.key]}
              onChange={(event) => setSources((current) => ({ ...current, [modality.key]: event.target.value }))}
              disabled={running || options[modality.key].length === 0}
              aria-label={`Select ${modality.label.toLowerCase()} dataset`}
            >
              <option value="">{options[modality.key].length ? "Select a registered source" : `No registered ${modality.label.toLowerCase()} data`}</option>
              {options[modality.key].map((dataset) => <option key={dataset.dataset_id} value={dataset.path}>{dataset.dataset_name}</option>)}
            </select>
            {sources[modality.key] ? <small className="source-select__note" title={sources[modality.key]}>{options[modality.key].find((dataset) => dataset.path === sources[modality.key])?.path}</small> : null}
          </label>
        ))}
      </div>

      <div className="source-control-panel__registry">
        <span>{datasets.length} registered source{datasets.length === 1 ? "" : "s"}</span>
        <button type="button" className="text-button" onClick={() => onNavigate("datasets")}>Registry <Icon name="arrow" size={13} /></button>
      </div>

      {demoStatus?.running && demoStatus.sources ? (
        <div className="source-control-panel__active">
          <span>Configured for {demoStatus.machine_id === machine?.machine_id ? "selected machine" : demoStatus.machine_id ?? "another machine"}</span>
          {modalityLabels.map((modality) => <div key={modality.key}><span>{modality.label}</span><strong>{demoStatus.sources[modality.key] ? "Configured" : "Not configured"}</strong></div>)}
        </div>
      ) : null}

      {!running && selectedCount === 0 ? (
        <p className="source-control-panel__notice">
          {datasets.length === 0
            ? "No datasets are registered. Enter a source path in Demo Controls to start a dataset session."
            : "Select at least one registered source, or enter a path in Demo Controls."}
        </p>
      ) : null}

      {demoError || actionError ? <p className="form-error" role="alert">{actionError ?? demoError}</p> : null}

      <div className="source-control-panel__actions">
        <button type="button" className="button button-primary" onClick={() => void start()} disabled={!canStart}>
          <Icon name="play" size={14} />{actionPending ? "Starting…" : "Start demo"}
        </button>
        <button type="button" className="button button-secondary" onClick={() => void stop()} disabled={!running || actionPending}>
          <Icon name="stop" size={13} />{actionPending ? "Working…" : "Stop"}
        </button>
      </div>

      <button type="button" className="source-control-panel__configure" onClick={() => onNavigate("demo")}>
        Configure source paths and playback <Icon name="arrow" size={13} />
      </button>
    </Panel>
  );
}
