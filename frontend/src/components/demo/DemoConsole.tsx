import { useEffect, useMemo, useState, type FormEvent } from "react";
import { api, isAbortError } from "../../services/api";
import type { DatasetInfo, DemoScenario, DemoStartRequest, DemoStatus, Machine, MachineVideoEntry, Modality } from "../../types";
import { DataState } from "../common/DataState";
import { Icon } from "../common/Icon";
import { Panel } from "../common/Panel";
import { SectionHeading } from "../common/SectionHeading";
import { StatusBadge } from "../common/StatusBadge";

const CUSTOM_SOURCE = "__custom_source__";

interface Props {
  machines: Machine[];
  datasets: DatasetInfo[];
  machineVideos: MachineVideoEntry[];
  machineVideosLoading?: boolean;
  machineVideosError?: string | null;
  selectedMachineId: string | null;
  status: DemoStatus | null;
  loading?: boolean;
  error?: string | null;
  onStart: (request: DemoStartRequest) => Promise<void>;
  onStop: () => Promise<void>;
}

export function DemoConsole({ machines, datasets, machineVideos, machineVideosLoading = false, machineVideosError = null, selectedMachineId, status, loading = false, error = null, onStart, onStop }: Props) {
  const [machineId, setMachineId] = useState(selectedMachineId ?? machines[0]?.machine_id ?? "");
  const [thermalSource, setThermalSource] = useState("");
  const [vibrationSource, setVibrationSource] = useState("");
  const [acousticSource, setAcousticSource] = useState("");
  const [thermalMachineVideoId, setThermalMachineVideoId] = useState("");
  const [vibrationScenarioId, setVibrationScenarioId] = useState("");
  const [acousticScenarioId, setAcousticScenarioId] = useState("");
  const [channel, setChannel] = useState("0");
  const [vibrationStartFile, setVibrationStartFile] = useState("");
  const [vibrationEndFile, setVibrationEndFile] = useState("");
  const [speed, setSpeed] = useState("1");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [scenarios, setScenarios] = useState<DemoScenario[]>([]);
  const [scenariosLoading, setScenariosLoading] = useState(true);
  const [scenariosError, setScenariosError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void api.demoScenarios({ signal: controller.signal }).then((items) => {
      setScenarios(items);
      setScenariosError(null);
    }).catch((scenarioError: unknown) => {
      if (isAbortError(scenarioError)) return;
      setScenariosError(scenarioError instanceof Error ? scenarioError.message : "Demo scenarios are unavailable.");
    }).finally(() => {
      if (!controller.signal.aborted) setScenariosLoading(false);
    });
    return () => controller.abort();
  }, []);

  // One visible entry per machine identity, even when multiple videos map
  // to the same name (e.g. two Honda Engine clips) - the registry still
  // keeps every underlying video mapped, this only picks the first
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

  function chooseMachineVideo(machineVideoId: string) {
    const entry = machineVideos.find((item) => item.machine_video_id === machineVideoId);
    setThermalMachineVideoId(machineVideoId);
    setThermalSource(entry?.path ?? "");
  }

  function chooseScenario(modality: Modality, scenarioId: string) {
    const scenario = scenarios.find((item) => item.scenario_id === scenarioId);
    const isCustom = scenarioId === CUSTOM_SOURCE;
    if (modality === "vibration") {
      setVibrationScenarioId(scenarioId);
      setVibrationSource(scenario?.source ?? "");
      setChannel(String(scenario?.channel ?? 0));
      setVibrationStartFile(scenario?.start_file == null ? "" : String(scenario.start_file));
      setVibrationEndFile(scenario?.end_file == null ? "" : String(scenario.end_file));
    } else {
      setAcousticScenarioId(scenarioId);
      setAcousticSource(scenario?.source ?? "");
    }
    if (isCustom) setFormError(null);
  }

  const optionsFor = (modality: Modality) => scenarios.filter((scenario) => scenario.modality === modality);
  const selectedScenario = (id: string) => scenarios.find((scenario) => scenario.scenario_id === id);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!machineId) { setFormError("Choose a machine before starting the demo."); return; }
    if (!thermalSource.trim() && !vibrationSource.trim() && !acousticSource.trim()) {
      setFormError("Choose or enter at least one source path. A session without a source cannot emit modality readings.");
      return;
    }
    const playback = Number(speed);
    const vibrationChannel = Number(channel);
    if (!Number.isFinite(playback) || playback <= 0) { setFormError("Playback speed must be greater than zero."); return; }
    if (!Number.isInteger(vibrationChannel) || vibrationChannel < 0) { setFormError("Vibration channel must be a non-negative integer."); return; }
    const startFile = vibrationStartFile.trim() === "" ? undefined : Number(vibrationStartFile);
    const endFile = vibrationEndFile.trim() === "" ? undefined : Number(vibrationEndFile);
    if (startFile !== undefined && (!Number.isInteger(startFile) || startFile < 0)) { setFormError("Vibration start file must be a non-negative integer."); return; }
    if (endFile !== undefined && (!Number.isInteger(endFile) || endFile < 0)) { setFormError("Vibration end file must be a non-negative integer."); return; }
    if (startFile !== undefined && endFile !== undefined && endFile < startFile) { setFormError("Vibration end file must be greater than or equal to its start file."); return; }
    setFormError(null);
    setSubmitting(true);
    try {
      await onStart({ machine_id: machineId, thermal_source: thermalSource.trim() || null, vibration_source: vibrationSource.trim() || null, acoustic_source: acousticSource.trim() || null, vibration_channel: vibrationChannel, vibration_start_file: startFile, vibration_end_file: endFile, playback_speed: playback });
    } catch (startError) {
      setFormError(startError instanceof Error ? startError.message : "Demo could not be started.");
    } finally { setSubmitting(false); }
  }

  async function stop() {
    setFormError(null);
    setSubmitting(true);
    try { await onStop(); } catch (stopError) { setFormError(stopError instanceof Error ? stopError.message : "Demo could not be stopped."); } finally { setSubmitting(false); }
  }

  return (
    <div className="page">
      <SectionHeading eyebrow="Dataset simulation" title="Demo control" description="Start one backend demo session and observe the same fusion output used by the live monitoring surface. A running session does not guarantee that every configured source is producing telemetry." action={<StatusBadge status={status?.running ? "demo" : "offline"} label={status?.running ? "Session running" : "Session idle"} />} />
      <div className="demo-layout">
        <Panel tone="paper" className="demo-form-panel">
          <div className="panel-title-row"><div><div className="panel-kicker panel-kicker--dark">Session configuration</div><h3>Choose source inputs</h3></div><span className="panel-title-row__hint">One global session</span></div>
          {loading ? <DataState tone="loading" title="Reading demo state" description="Checking the backend session." surface="light" compact /> : null}
          {error ? <DataState tone="error" title="Demo status unavailable" description={error} surface="light" compact /> : null}
          <form onSubmit={submit} className="demo-form">
            <label><span>Machine *</span><select value={machineId} onChange={(event) => setMachineId(event.target.value)} disabled={Boolean(status?.running)}><option value="">Select a machine</option>{machines.map((machine) => <option key={machine.machine_id} value={machine.machine_id}>{machine.machine_name}</option>)}</select></label>
            <label>
              <span>Machine (thermal video)</span>
              <select value={thermalMachineVideoId} onChange={(event) => chooseMachineVideo(event.target.value)} disabled={Boolean(status?.running) || machineOptions.length === 0}>
                <option value="">{machineOptions.length ? "— No machine selected —" : "No machines registered"}</option>
                {machineOptions.map((entry) => <option key={entry.machine_video_id} value={entry.machine_video_id}>{entry.name}</option>)}
              </select>
              <small>Predefined machine list, mapped to its prerecorded thermal video automatically - no manual path or machine name entry.</small>
            </label>
            {machineVideosLoading ? <DataState tone="loading" title="Loading machine registry" description="Reading the machine/video mapping." surface="light" compact /> : null}
            {machineVideosError ? <DataState tone="error" title="Machine registry unavailable" description={machineVideosError} surface="light" compact /> : null}
            <label><span>Vibration source</span><select value={vibrationScenarioId} onChange={(event) => chooseScenario("vibration", event.target.value)} disabled={Boolean(status?.running)}><option value="">— No vibration source —</option>{optionsFor("vibration").map((scenario) => <option key={scenario.scenario_id} value={scenario.scenario_id}>{scenario.label}</option>)}<option value={CUSTOM_SOURCE}>Custom path…</option></select>{vibrationScenarioId === CUSTOM_SOURCE ? <input list="vibration-dataset-options" value={vibrationSource} onChange={(event) => setVibrationSource(event.target.value)} disabled={Boolean(status?.running)} placeholder="Local dataset path" /> : null}{selectedScenario(vibrationScenarioId)?.notes ? <small>{selectedScenario(vibrationScenarioId)?.notes}</small> : null}</label>
            <datalist id="vibration-dataset-options">{datasets.filter((dataset) => dataset.modality.toLowerCase() === "vibration").map((dataset) => <option key={dataset.dataset_id} value={dataset.path}>{dataset.dataset_name}</option>)}</datalist>
            <label><span>Acoustic source</span><select value={acousticScenarioId} onChange={(event) => chooseScenario("acoustic", event.target.value)} disabled={Boolean(status?.running)}><option value="">— No acoustic source —</option>{optionsFor("acoustic").map((scenario) => <option key={scenario.scenario_id} value={scenario.scenario_id}>{scenario.label}</option>)}<option value={CUSTOM_SOURCE}>Custom path…</option></select>{acousticScenarioId === CUSTOM_SOURCE ? <input list="acoustic-dataset-options" value={acousticSource} onChange={(event) => setAcousticSource(event.target.value)} disabled={Boolean(status?.running)} placeholder="Local WAV path" /> : null}{selectedScenario(acousticScenarioId)?.notes ? <small>{selectedScenario(acousticScenarioId)?.notes}</small> : null}</label>
            <datalist id="acoustic-dataset-options">{datasets.filter((dataset) => dataset.modality.toLowerCase() === "acoustic").map((dataset) => <option key={dataset.dataset_id} value={dataset.path}>{dataset.dataset_name}</option>)}</datalist>
            {scenariosLoading ? <DataState tone="loading" title="Loading source scenarios" description="Reading the backend-registered demo presets." surface="light" compact /> : null}
            {scenariosError ? <DataState tone="error" title="Scenario registry unavailable" description={`${scenariosError} Custom source paths remain available.`} surface="light" compact /> : null}
            {vibrationScenarioId === CUSTOM_SOURCE ? <div className="demo-form__row"><label><span>Start file (optional)</span><input inputMode="numeric" value={vibrationStartFile} onChange={(event) => setVibrationStartFile(event.target.value)} disabled={Boolean(status?.running)} /></label><label><span>End file (optional)</span><input inputMode="numeric" value={vibrationEndFile} onChange={(event) => setVibrationEndFile(event.target.value)} disabled={Boolean(status?.running)} /></label></div> : null}
            <div className="demo-form__row"><label><span>Vibration channel</span><input inputMode="numeric" value={channel} onChange={(event) => setChannel(event.target.value)} disabled={Boolean(status?.running) || (vibrationScenarioId !== "" && vibrationScenarioId !== CUSTOM_SOURCE)} /></label><label><span>Playback speed</span><input inputMode="decimal" value={speed} onChange={(event) => setSpeed(event.target.value)} disabled={Boolean(status?.running)} /></label></div>
            {formError ? <p className="form-error" role="alert">{formError}</p> : null}
            <div className="demo-form__actions">{status?.running ? <button type="button" className="button button-secondary" onClick={stop} disabled={submitting || loading}><Icon name="stop" size={15} />{submitting ? "Stopping…" : "Stop demo"}</button> : <button type="submit" className="button button-primary" disabled={submitting || loading || machines.length === 0 || status === null}><Icon name="play" size={15} />{submitting ? "Starting…" : "Start demo"}</button>}</div>
          </form>
        </Panel>

        <Panel tone="ink" className="demo-state-panel">
          <div className="panel-kicker"><span>Runtime state</span><span>Demo API</span></div>
          <div className="demo-state-panel__mark"><span className={status?.running ? "is-running" : ""} /><Icon name="pulse" size={22} /></div>
          <h2>{status?.running ? "Session is running" : "No active session"}</h2>
          <p>{status?.running ? "Telemetry will arrive when a configured reader emits a valid feature set. Watch freshness and missing modalities in the command surface." : "The backend is idle. Start a session to stream dataset-backed fusion envelopes."}</p>
          <div className="demo-state-panel__list"><div><span>Machine</span><strong>{machines.find((machine) => machine.machine_id === status?.machine_id)?.machine_name ?? status?.machine_id ?? "—"}</strong></div><div><span>Mode</span><strong>{status?.mode ?? "demo"}</strong></div><div><span>Started</span><strong>{status?.started_at ? new Date(status.started_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "—"}</strong></div></div>
          {status?.running && status.sources ? <div className="demo-sources"><span className="muted-label muted-label--light">Configured sources</span>{Object.entries(status.sources).map(([key, value]) => <div key={key}><span>{key}</span><strong>{value ? "configured" : "not configured"}</strong></div>)}</div> : null}
        </Panel>
      </div>
    </div>
  );
}
