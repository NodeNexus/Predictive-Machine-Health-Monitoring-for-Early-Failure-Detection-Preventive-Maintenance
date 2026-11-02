import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, isAbortError, isApiError, thermalFeedImageUrl, thermalVideoUrl } from "../../services/api";
import { useTelemetry, type ConnectionState } from "../../services/useTelemetry";
import type {
  DemoScenario, DemoStatus, Machine, MachineHealthState, MachineVideoEntry, Modality, PlaybackProgress,
  TelemetryPayload, ThermalEvaluation, ThermalFeedEntry,
} from "../../types";
import { scenarioKnownCondition, videoKnownCondition } from "./knownCondition";
import "./dashboard.css";

type InputKey = "vibration" | "sound" | "thermal";
type Selection = Record<InputKey, string>;

const INPUT_KEYS: InputKey[] = ["vibration", "sound", "thermal"];
const MODALITY: Record<InputKey, Modality> = { vibration: "vibration", sound: "acoustic", thermal: "thermal" };
const INPUT_TITLES: Record<InputKey, string> = { vibration: "Vibration", sound: "Sound", thermal: "Thermal video" };
const NO_SELECTION: Selection = { vibration: "", sound: "", thermal: "" };
const STALE_MS = 7000;
const NO_DATA_MS = 30000; // the first thermal result waits for the model to load
const MAX_EVENTS = 8;
const STORE_KEY = "idealab.dashboard.run";

// ---------------------------------------------------------------- persistence

/** The run this browser started, kept so labels survive a page reload. Only trusted when the session id still matches. */
interface StoredRun { sessionId: string | null; machineId: string; selection: Selection; localStart: number }

function loadRun(): StoredRun | null {
  try {
    const raw = window.localStorage.getItem(STORE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredRun>;
    const sel = parsed.selection;
    if (!sel || typeof parsed.machineId !== "string" || typeof parsed.localStart !== "number") return null;
    if (!INPUT_KEYS.every((key) => typeof sel[key] === "string")) return null;
    return { sessionId: parsed.sessionId ?? null, machineId: parsed.machineId, selection: sel, localStart: parsed.localStart };
  } catch {
    return null;
  }
}

function saveRun(run: StoredRun | null) {
  try {
    if (run) window.localStorage.setItem(STORE_KEY, JSON.stringify(run));
    else window.localStorage.removeItem(STORE_KEY);
  } catch {
    /* storage unavailable: labels simply will not survive a reload */
  }
}

// -------------------------------------------------------------------- helpers

function errorMessage(error: unknown) {
  if (isApiError(error)) return error.detail ?? error.message;
  return error instanceof Error ? error.message : "The backend could not be reached.";
}

/** Plain-language reason a backend call failed, so "unreachable" is never reported for a server that did answer. */
function describeBackendFailure(error: unknown): { reachable: boolean; text: string } {
  if (isApiError(error)) {
    if (error.kind === "network") return { reachable: false, text: "The connection was refused or lost. Is the backend running on port 8000?" };
    if (error.kind === "timeout") return { reachable: false, text: "The backend did not answer in time. It may be busy or stuck." };
    if (error.kind === "http" && [502, 503, 504].includes(error.status ?? 0)) {
      return { reachable: false, text: "The dev server could not reach the backend. Is it running on port 8000?" };
    }
    if (error.kind === "invalid_json") return { reachable: true, text: "Something answered, but not with the monitoring API (the reply was not JSON). Check that /api is proxied to the backend." };
    if (error.kind === "invalid_response") return { reachable: true, text: `The backend answered with an unexpected response shape${error.detail ? ` (${error.detail})` : ""}.` };
    const detail = error.detail ?? "";
    if (error.kind === "http" && (detail.trimStart().startsWith("<") || detail.length > 160)) {
      return { reachable: true, text: `Something answered with HTTP ${error.status ?? "error"} that is not the monitoring API. Another program may be using port 8000.` };
    }
    return { reachable: true, text: `The backend answered with an error: ${detail || error.message}` };
  }
  return { reachable: false, text: error instanceof Error ? error.message : "The backend could not be reached." };
}

const capitalise = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);
const percent = (value: number) => `${Math.round(value * 1000) / 10}%`; // one decimal, so 99.7% is never shown as 100%
const norm = (path: string | null | undefined) => (path ?? "").replace(/\\/g, "/").toLowerCase();
const lastSegment = (path: string) => path.split(/[\\/]/).filter(Boolean).slice(-2).join("/");

/** The backend serializes UTC times without a zone marker; treat those as UTC. */
function parseUtc(value: string): number {
  return Date.parse(/(Z|[+-]\d\d:?\d\d)$/.test(value) ? value : `${value}Z`);
}

function formatDuration(ms: number) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mmss = `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return h > 0 ? `${h}:${mmss}` : mmss;
}

function describeProgress(p: PlaybackProgress) {
  const place = p.unit === "seconds"
    ? `${formatDuration(p.position * 1000)} / ${formatDuration(p.total * 1000)}`
    : `file ${Math.min(p.position, p.total)} / ${p.total}`;
  return p.loop > 1 ? `${place} · replay ${p.loop}` : place;
}

const FEED_LABEL: Record<ConnectionState, string> = {
  open: "Connected",
  connecting: "Connecting",
  reconnecting: "Reconnecting",
  error: "Error",
  closed: "Disconnected",
};

// ----------------------------------------------------------------- run model

interface RunSpec {
  selection: Selection;
  /** Names for sources that could not be matched to a catalogue entry (a session started elsewhere). */
  fallbackLabels: Partial<Record<InputKey, string>>;
}

interface InputRow {
  key: InputKey;
  selected: boolean;
  runLabel: string | null;
  known: string | null;
}

function buildRows(spec: RunSpec, scenarios: DemoScenario[], videos: MachineVideoEntry[]): InputRow[] {
  return INPUT_KEYS.map((key): InputRow => {
    const id = spec.selection[key];
    const fallback = spec.fallbackLabels[key] ?? null;
    if (!id) return { key, selected: fallback !== null, runLabel: fallback, known: null };
    if (key === "thermal") {
      const video = videos.find((item) => item.machine_video_id === id);
      return { key, selected: true, runLabel: video ? `${video.name} (clip ${video.video_id})` : id, known: videoKnownCondition(video) };
    }
    const scenario = scenarios.find((item) => item.scenario_id === id);
    return { key, selected: true, runLabel: scenario?.label ?? id, known: scenarioKnownCondition(scenario) };
  });
}

/** Best-effort identification of a session this page did not start, from the backend's own source paths. */
function identifyAdopted(status: DemoStatus, scenarios: DemoScenario[], videos: MachineVideoEntry[], vibrationSource: string | undefined): RunSpec {
  const selection: Selection = { ...NO_SELECTION };
  const fallbackLabels: RunSpec["fallbackLabels"] = {};
  const sources = status.sources ?? {};

  const vibrationPath = sources.vibration;
  if (vibrationPath) {
    let candidates = scenarios.filter((s) => s.modality === "vibration" && norm(s.source) === norm(vibrationPath));
    const range = vibrationSource ? /\[(\d+):(-?\d+)\]$/.exec(vibrationSource) : null;
    if (candidates.length > 1 && range) {
      const ranged = candidates.filter((s) => String(s.start_file ?? 0) === range[1] && String(s.end_file ?? -1) === range[2]);
      if (ranged.length) candidates = ranged;
    }
    if (candidates.length === 1) selection.vibration = candidates[0].scenario_id;
    else fallbackLabels.vibration = `Vibration run (${lastSegment(vibrationPath)})`;
  }
  if (sources.acoustic) {
    const match = scenarios.find((s) => s.modality === "acoustic" && norm(s.source) === norm(sources.acoustic));
    if (match) selection.sound = match.scenario_id;
    else fallbackLabels.sound = `Sound clip (${lastSegment(sources.acoustic)})`;
  }
  if (sources.thermal) {
    const match = videos.find((v) => norm(v.path) === norm(sources.thermal));
    if (match) selection.thermal = match.machine_video_id;
    else fallbackLabels.thermal = `Video (${lastSegment(sources.thermal)})`;
  }
  return { selection, fallbackLabels };
}

// ------------------------------------------------------------------ readings

type Reading =
  | { kind: "unselected" }
  | { kind: "idle" }
  | { kind: "waiting" }
  | { kind: "unavailable"; reason: string; guess: string | null; confidence: number | null; reliability: string | null; version: string | null }
  | { kind: "value"; label: string; detail: string | null; confidence: number | null; reliability: string | null; version: string | null };

function readingFor(key: InputKey, row: InputRow, payload: TelemetryPayload | null, running: boolean): Reading {
  if (!row.selected) return { kind: "unselected" };
  if (!payload) return { kind: running ? "waiting" : "idle" };
  if (key === "vibration" || key === "sound") {
    const block = key === "vibration" ? payload.vibration : payload.acoustic;
    if (!block) return { kind: "waiting" };
    if (block.ml_prediction === null) {
      return { kind: "unavailable", reason: block.ml_reliability === "unavailable" ? "Model unavailable" : "No confident prediction", guess: null, confidence: block.ml_confidence, reliability: block.ml_reliability, version: block.ml_model_version };
    }
    return { kind: "value", label: capitalise(block.ml_prediction), detail: null, confidence: block.ml_confidence, reliability: block.ml_reliability, version: block.ml_model_version };
  }
  const thermal = payload.thermal;
  if (!thermal) return { kind: "waiting" };
  if (thermal.ml_prediction === null) {
    return { kind: "unavailable", reason: thermal.ml_reliability === "unavailable" && thermal.ml_confidence === null ? "Model unavailable" : "No confident class", guess: thermal.ml_top_class, confidence: thermal.ml_confidence, reliability: thermal.ml_reliability, version: thermal.model_version };
  }
  const load = thermal.ml_load_context ? thermal.ml_load_context.toLowerCase() : null; // backend text may already end in "load"
  const detail = [thermal.ml_condition, load ? (/load$/.test(load) ? load : `${load} load`) : null].filter(Boolean).join(", ");
  return { kind: "value", label: thermal.ml_prediction, detail: detail || null, confidence: thermal.ml_confidence, reliability: thermal.ml_reliability, version: thermal.model_version };
}

type Deviation =
  | { kind: "waiting" }
  | { kind: "missing" }
  | { kind: "learning" }
  | { kind: "value"; value: number; features: string[] };

/** Per-input deviation from that input's own baseline, from the backend's per-modality health contributions. */
function deviationFor(modality: Modality, health: MachineHealthState | null): Deviation {
  if (!health) return { kind: "waiting" };
  if (health.missing_modalities.includes(modality)) return { kind: "missing" };
  const value = health.modality_contributions[modality];
  if (value === undefined) return { kind: "learning" };
  const features = health.evidence
    .filter((item) => item.modality === modality && item.feature !== "baseline")
    .slice(0, 2)
    .map((item) => (item.deviation === null ? item.feature : `${item.feature} ${item.deviation >= 0 ? "+" : "−"}${Math.abs(item.deviation).toFixed(1)}σ`));
  return { kind: "value", value, features };
}

/** Short per-input baseline-change line, from per-modality backend health data (vibration and sound only). */
function deriveDeviation(key: InputKey, health: MachineHealthState | null, running: boolean): string | null {
  if (key === "thermal" || !running) return null;
  const deviation = deviationFor(MODALITY[key], health);
  if (deviation.kind === "value") return `Change from own baseline ${deviation.value.toFixed(2)} of 1${deviation.features.length ? ` · ${deviation.features.join(", ")}` : ""}`;
  return deviation.kind === "learning" ? "Learning own baseline" : null;
}

interface LoggedEvent { at: string; type: string; status: string | null }

type Tone = "ok" | "warn" | "bad" | "neutral" | "info";

/** Colour tone of a model result. Always rendered with a symbol and the word itself, never colour alone. */
function toneFor(key: InputKey, label: string): Tone {
  const l = label.toLowerCase();
  if (key === "vibration") return l === "healthy" ? "ok" : l === "degrading" ? "warn" : l === "severe" ? "bad" : "neutral";
  if (key === "sound") return l === "normal" ? "ok" : l === "anomaly" ? "bad" : "neutral";
  return "info"; // thermal class codes are not validated for these clips, so they are not coloured good/bad
}

function healthTone(status: string): Tone {
  return status === "normal" ? "ok" : status === "warning" ? "warn" : status === "critical" ? "bad" : "neutral";
}

function eventTone(event: LoggedEvent): string {
  if (event.type === "event_cleared") return "ev--ok";
  if (event.type === "event_started") return event.status === "critical" ? "ev--bad" : "ev--warn";
  return "";
}

// ----------------------------------------------------------- saved test results

const CLASS_CODES = ["CFL", "CML", "CNL", "HFL", "HML", "HNL"];

function ModelResults() {
  const [evaluation, setEvaluation] = useState<{ data: ThermalEvaluation | null; error: string | null; done: boolean }>({ data: null, error: null, done: false });
  const [feed, setFeed] = useState<{ data: ThermalFeedEntry[]; error: string | null; done: boolean }>({ data: [], error: null, done: false });

  useEffect(() => {
    const controller = new AbortController();
    const options = { signal: controller.signal, timeoutMs: 60000 };
    void api.thermalEvaluation(options)
      .then((data) => setEvaluation({ data, error: null, done: true }))
      .catch((error: unknown) => { if (!isAbortError(error)) setEvaluation({ data: null, error: errorMessage(error), done: true }); });
    void api.thermalImageFeed(options)
      .then((data) => setFeed({ data, error: null, done: true }))
      .catch((error: unknown) => { if (!isAbortError(error)) setFeed({ data: [], error: errorMessage(error), done: true }); });
    return () => controller.abort();
  }, []);

  // One held-out example per class, in a fixed class order.
  const examples = useMemo(() => {
    const seen = new Set<string>();
    return feed.data
      .filter((entry) => {
        const cls = entry.true_class ?? "";
        if (!cls || seen.has(cls)) return false;
        seen.add(cls);
        return true;
      })
      .sort((a, b) => CLASS_CODES.indexOf(a.true_class ?? "") - CLASS_CODES.indexOf(b.true_class ?? ""));
  }, [feed.data]);

  const ev = evaluation.data;
  return (
    <section className="panel results" aria-labelledby="results-title">
      <div className="panel-head">
        <h2 id="results-title">Model test results</h2>
        <span className="tag">Thermal classifier{ev?.model_version ? ` · ${ev.model_version}` : ""}</span>
        <span className="push note">Held-out still images{ev?.test_count ? ` (${ev.test_count})` : ""}. Accuracy on the demo videos has not been measured.</span>
      </div>
      <div className="results-body">
        <div className="metrics">
          {!evaluation.done ? <span className="muted">Loading saved results&hellip;</span> : null}
          {evaluation.error ? <span className="muted">Unavailable: {evaluation.error}</span> : null}
          {ev ? (
            <>
              <div className="metric"><span className="metric-v">{percent(ev.accuracy)}</span><span className="metric-l">Accuracy</span></div>
              <div className="metric"><span className="metric-v">{ev.macro_f1.toFixed(3)}</span><span className="metric-l">Macro-F1</span></div>
              <div className="metric"><span className="metric-v">{percent(ev.top3_accuracy)}</span><span className="metric-l">Top-3 accuracy</span></div>
            </>
          ) : null}
        </div>
        <div className="examples" aria-label="Held-out test examples">
          {!feed.done ? <span className="muted">Loading held-out examples&hellip;</span> : null}
          {feed.error ? <span className="muted">Examples unavailable: {feed.error}</span> : null}
          {examples.map((entry) => {
            const predicted = entry.ml_prediction;
            return (
              <figure className="example" key={entry.image_id}>
                <img src={thermalFeedImageUrl(entry.image_id)} alt={`Held-out test image, known class ${entry.true_class}`} loading="lazy" />
                <figcaption>
                  <span>Known <strong>{entry.true_class}</strong></span>
                  <span className={predicted === null ? "muted" : predicted === entry.true_class ? "ok" : "miss"}>
                    {predicted !== null
                      ? `Model ${predicted}${entry.ml_confidence !== null ? ` ${percent(entry.ml_confidence)}` : ""}`
                      : entry.ml_top_class ? `Guess ${entry.ml_top_class}${entry.ml_confidence !== null ? ` ${percent(entry.ml_confidence)}` : ""} (low)` : "No confident class"}
                  </span>
                </figcaption>
              </figure>
            );
          })}
        </div>
      </div>
    </section>
  );
}

// ----------------------------------------------------------------- component

interface PlayerState { key: string | null; state: "loading" | "playing" | "buffering" | "error"; time: number; duration: number; message: string | null }

export function Dashboard() {
  const [scenarios, setScenarios] = useState<DemoScenario[]>([]);
  const [videos, setVideos] = useState<MachineVideoEntry[]>([]);
  const [catalog, setCatalog] = useState<{ state: "loading" | "ready" | "error"; error: string | null }>({ state: "loading", error: null });
  const [form, setForm] = useState<Selection>(NO_SELECTION);
  const [started, setStarted] = useState<StoredRun | null>(loadRun);
  const [status, setStatus] = useState<DemoStatus | null>(null);
  const [backend, setBackend] = useState<"checking" | "online" | "unreachable" | "error">("checking");
  const [statusError, setStatusError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [eventLog, setEventLog] = useState<LoggedEvent[]>([]);
  const [player, setPlayer] = useState<PlayerState>({ key: null, state: "loading", time: 0, duration: 0, message: null });
  const [now, setNow] = useState(() => Date.now());
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const wasRunning = useRef(false);
  const stopRequested = useRef(false);
  const missedPolls = useRef(0);

  const running = backend === "online" && Boolean(status?.running);
  const adopted = running && (!started || started.sessionId !== status?.session_id);
  const machineId = status?.machine_id ?? started?.machineId ?? null;

  const onPayload = useCallback((payload: TelemetryPayload) => {
    if (payload.events.length === 0) return;
    setEventLog((current) => [
      ...payload.events.map((event) => ({ at: payload.timestamp, type: event.type, status: typeof event.status === "string" ? event.status : null })),
      ...current,
    ].slice(0, MAX_EVENTS));
  }, []);
  // The telemetry socket only exists while a session runs, so Stop closes it and Start opens a fresh one.
  const telemetry = useTelemetry({ machineId, enabled: running, reconnect: true, reconnectMaxDelayMs: 5000, onPayload });
  const latest = telemetry.latest;

  // Recorded runs the backend offers.
  useEffect(() => {
    const controller = new AbortController();
    const options = { signal: controller.signal, timeoutMs: 10000 };
    void Promise.all([api.demoScenarios(options), api.machineVideos(options)])
      .then(([scenarioList, videoList]) => {
        setScenarios(scenarioList);
        setVideos(videoList);
        setCatalog({ state: "ready", error: null });
      })
      .catch((error: unknown) => {
        if (!isAbortError(error)) setCatalog({ state: "error", error: errorMessage(error) });
      });
    return () => controller.abort();
  }, []);

  // Backend reachability (health) and session state (status), polled so changes made elsewhere are reflected.
  const refreshStatus = useCallback(async (): Promise<DemoStatus | null> => {
    try {
      await api.health({ timeoutMs: 8000 });
      missedPolls.current = 0;
    } catch (error) {
      if (isAbortError(error)) return null;
      const failure = describeBackendFailure(error);
      missedPolls.current += 1;
      if (!failure.reachable && missedPolls.current < 2) return null; // keep the last known state for one poll
      wasRunning.current = false;
      setBackend(failure.reachable ? "error" : "unreachable");
      setStatusError(failure.text);
      return null;
    }
    try {
      const next = await api.demoStatus({ timeoutMs: 8000 });
      if (wasRunning.current && !next.running && !stopRequested.current) {
        setNotice("The test is no longer running on the backend (it was stopped elsewhere or the backend restarted).");
      }
      wasRunning.current = next.running;
      setStatus(next);
      setBackend("online");
      setStatusError(null);
      return next;
    } catch (error) {
      if (isAbortError(error)) return null;
      wasRunning.current = false;
      setBackend("error");
      setStatusError(`Session state unavailable. ${describeBackendFailure(error).text}`);
      return null;
    }
  }, []);

  useEffect(() => {
    const first = window.setTimeout(() => void refreshStatus(), 0);
    const id = window.setInterval(() => void refreshStatus(), 3000);
    return () => { window.clearTimeout(first); window.clearInterval(id); };
  }, [refreshStatus]);

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  // The video follows the real session: it plays while the backend is processing a thermal source and is released when it stops.
  const videoSrc = running && status?.sources?.thermal ? `${thermalVideoUrl()}?session=${encodeURIComponent(status.session_id ?? "active")}` : null;
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    if (!videoSrc) {
      video.pause();
      video.removeAttribute("src");
      video.load();
    } else {
      void video.play().catch(() => undefined); // autoplay is allowed for muted video; failures surface through onError
    }
  }, [videoSrc]);
  const view: PlayerState = videoSrc && player.key === videoSrc ? player : { key: videoSrc, state: "loading", time: 0, duration: 0, message: null };

  // What the Test window and Output describe.
  const spec: RunSpec = useMemo(() => {
    if (running && status) {
      if (!adopted && started) return { selection: started.selection, fallbackLabels: {} };
      return identifyAdopted(status, scenarios, videos, latest?.vibration?.source);
    }
    return { selection: form, fallbackLabels: {} };
  }, [adopted, form, latest, running, scenarios, started, status, videos]);

  const rows = useMemo(() => buildRows(spec, scenarios, videos), [scenarios, spec, videos]);
  const selectedRows = rows.filter((row) => row.selected);
  const single = selectedRows.length === 1;

  const sessionStart = running ? (!adopted && started ? started.localStart : status?.started_at ? parseUtc(status.started_at) : NaN) : NaN;
  const elapsed = Number.isFinite(sessionStart) ? now - sessionStart : null;
  // The hook keeps the last message when a machine is reused, so only trust data that arrived after this session began.
  const hasSessionData = running && telemetry.lastMessageAt !== null && Number.isFinite(sessionStart) && telemetry.lastMessageAt >= sessionStart;
  const current = hasSessionData ? latest : null;
  const readings = rows.map((row) => readingFor(row.key, row, current, running));
  const sinceMessage = telemetry.lastMessageAt === null ? null : now - telemetry.lastMessageAt;
  const stale = running && hasSessionData && telemetry.connection === "open" && sinceMessage !== null && sinceMessage > STALE_MS;
  const noDataYet = running && !hasSessionData && elapsed !== null && elapsed > NO_DATA_MS;
  const feedDown = running && telemetry.connection !== "open" && telemetry.connection !== "connecting";
  const lastUpdate = current ? new Date(current.timestamp) : null;
  const health = current?.health ?? null;

  const setChoice = useCallback((key: InputKey, value: string) => {
    setForm((currentForm) => ({ ...currentForm, [key]: value }));
    setActionError(null);
  }, []);

  /** One machine per distinct choice of sources, created only if it does not exist yet and reused on every later Start. */
  const ensureMachine = useCallback(async (selection: Selection): Promise<Machine> => {
    const name = `Dashboard replay: ${INPUT_KEYS.map((key) => `${key}=${selection[key] || "none"}`).join(", ")}`;
    const existing = (await api.listMachines({ timeoutMs: 8000 })).find((machine) => machine.machine_name === name);
    return existing ?? api.createMachine({ machine_name: name }, { timeoutMs: 8000 });
  }, []);

  const start = useCallback(async () => {
    if (backend !== "online") { setActionError("The backend is not reachable, so a test cannot start."); return; }
    const vibration = scenarios.find((item) => item.scenario_id === form.vibration);
    const sound = scenarios.find((item) => item.scenario_id === form.sound);
    const video = videos.find((item) => item.machine_video_id === form.thermal);
    if (!vibration && !sound && !video) { setActionError("Choose at least one recorded run to replay."); return; }
    setBusy(true);
    setActionError(null);
    setNotice(null);
    try {
      const machine = await ensureMachine(form);
      const next = await api.startDemo({
        machine_id: machine.machine_id,
        vibration_source: vibration?.source ?? null,
        vibration_channel: vibration?.channel ?? 0,
        vibration_start_file: vibration?.start_file ?? undefined,
        vibration_end_file: vibration?.end_file ?? undefined,
        acoustic_source: sound?.source ?? null,
        thermal_source: video?.path ?? null,
        playback_speed: 1,
      }, { timeoutMs: 15000 });
      const run: StoredRun = { sessionId: next.session_id, machineId: machine.machine_id, selection: { ...form }, localStart: Date.now() };
      saveRun(run);
      setStarted(run);
      setEventLog([]);
      stopRequested.current = false;
      wasRunning.current = next.running;
      setStatus(next);
      setBackend("online");
    } catch (error) {
      if (isApiError(error) && error.status === 409) {
        setActionError("A test is already running on the backend. It is shown here instead.");
        void refreshStatus();
      } else {
        setActionError(errorMessage(error));
      }
    } finally {
      setBusy(false);
    }
  }, [backend, ensureMachine, form, refreshStatus, scenarios, videos]);

  const stop = useCallback(async () => {
    setBusy(true);
    setActionError(null);
    stopRequested.current = true;
    try {
      const next = await api.stopDemo({ timeoutMs: 10000 });
      wasRunning.current = next.running;
      setStatus(next);
      setBackend("online");
      setEventLog([]);
    } catch (error) {
      setActionError(`Stop could not be confirmed: ${errorMessage(error)}`);
      void refreshStatus(); // resync with whatever the backend is really doing
    } finally {
      setBusy(false);
      stopRequested.current = false;
    }
  }, [refreshStatus]);

  const optionsFor = (modality: "vibration" | "acoustic") => scenarios.filter((item) => item.modality === modality);
  const ready = catalog.state === "ready";
  const locked = running || busy;
  const formValue = (key: InputKey) => (running ? spec.selection[key] : form[key]);
  const backendLabel = backend === "online" ? "Online" : backend === "checking" ? "Checking" : backend === "unreachable" ? "Unreachable" : "Error";
  const feedLabel = !running ? "Idle" : FEED_LABEL[telemetry.connection];
  const thermalRow = rows.find((row) => row.key === "thermal");
  const thermalProgress = current?.progress.thermal;
  const progressRatio = view.duration > 0 ? Math.min(1, view.time / view.duration) : 0;

  return (
    <div className="dash">
      <header className="bar">
        <div className="bar-title">Multimodal Machine Health Monitoring and Anomaly Detection</div>
        <span className="badge" title="Prerecorded files replayed through the backend">DEMO MODE</span>
        <div className="bar-state">
          <span className={"state " + (backend === "online" ? "state--ok" : "state--bad")}>Backend: {backendLabel}</span>
          <span className={"state " + (running ? "state--ok" : "")}>{running ? "Test running" : "Test stopped"}</span>
          <span className={"state " + (running ? (telemetry.connection === "open" ? "state--ok" : "state--bad") : "")}>Feed: {feedLabel}</span>
        </div>
      </header>

      {(backend === "unreachable" || backend === "error") ? <p className="alert" role="alert">{backend === "unreachable" ? "Backend cannot be reached." : "Backend is responding with a problem."} {statusError}</p> : null}
      {notice ? <p className="alert" role="alert">{notice}</p> : null}
      {feedDown ? <p className="alert" role="alert">Telemetry feed {FEED_LABEL[telemetry.connection].toLowerCase()}; readings may be out of date.</p> : null}
      {stale && sinceMessage !== null ? <p className="alert" role="alert">No new data for {Math.round(sinceMessage / 1000)} s; readings may be out of date.</p> : null}
      {noDataYet ? <p className="alert" role="alert">Running, but no readings have arrived yet.</p> : null}
      {telemetry.error?.kind === "invalid_payload" ? <p className="alert" role="alert">A malformed telemetry message was ignored.</p> : null}

      <main className="grid">
        {/* INPUT */}
        <section className="panel input" aria-labelledby="input-title">
          <div className="panel-head"><h2 id="input-title">Input</h2></div>
          {catalog.state === "loading" ? <p className="muted">Loading runs&hellip;</p> : null}
          {catalog.state === "error" ? <p className="error" role="alert">Runs could not be loaded: {catalog.error}</p> : null}
          <label className="field">
            <span>Machine video</span>
            <select className={formValue("thermal") ? "is-set" : undefined} value={formValue("thermal")} onChange={(e) => setChoice("thermal", e.target.value)} disabled={locked || !ready}>
              <option value="">None</option>
              {videos.map((item) => <option key={item.machine_video_id} value={item.machine_video_id}>{item.name} (clip {item.video_id})</option>)}
            </select>
          </label>
          <label className="field">
            <span>Vibration run</span>
            <select className={formValue("vibration") ? "is-set" : undefined} value={formValue("vibration")} onChange={(e) => setChoice("vibration", e.target.value)} disabled={locked || !ready}>
              <option value="">None</option>
              {optionsFor("vibration").map((item) => <option key={item.scenario_id} value={item.scenario_id}>{item.label}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Sound clip</span>
            <select className={formValue("sound") ? "is-set" : undefined} value={formValue("sound")} onChange={(e) => setChoice("sound", e.target.value)} disabled={locked || !ready}>
              <option value="">None</option>
              {optionsFor("acoustic").map((item) => <option key={item.scenario_id} value={item.scenario_id}>{item.label}</option>)}
            </select>
          </label>
          <div className="actions">
            <button type="button" className="btn btn--primary" onClick={() => void start()} disabled={busy || running || !ready || backend !== "online"}>Start test</button>
            <button type="button" className="btn btn--stop" onClick={() => void stop()} disabled={busy || !running}>Stop</button>
          </div>
          {actionError ? <p className="error" role="alert">{actionError}</p> : null}
        </section>

        {/* TEST WINDOW */}
        <section className="panel window" aria-labelledby="window-title">
          <div className="panel-head">
            <h2 id="window-title">Test window</h2>
            {thermalRow?.selected ? <span className="tag">{thermalRow.runLabel}{thermalRow.known ? ` · ${thermalRow.known}` : ""}</span> : null}
            <span className="push">Elapsed <strong className="num">{elapsed !== null ? formatDuration(elapsed) : "--:--"}</strong></span>
          </div>
          <div className="stage">
            <video
              ref={videoRef}
              className={"video" + (videoSrc ? "" : " video--hidden")}
              src={videoSrc ?? undefined}
              muted
              loop
              playsInline
              autoPlay
              preload="auto"
              aria-label="Selected machine video, replayed"
              onPlaying={() => setPlayer((p) => ({ ...(p.key === videoSrc ? p : { time: 0, duration: 0, message: null }), key: videoSrc, state: "playing" }))}
              onWaiting={() => setPlayer((p) => ({ ...(p.key === videoSrc ? p : { time: 0, duration: 0, message: null }), key: videoSrc, state: "buffering" }))}
              onTimeUpdate={(e) => {
                const v = e.currentTarget;
                setPlayer((p) => ({ key: videoSrc, state: p.key === videoSrc && p.state !== "loading" ? p.state : "playing", time: v.currentTime, duration: Number.isFinite(v.duration) ? v.duration : 0, message: null }));
              }}
              onError={(e) => {
                const err = e.currentTarget.error;
                setPlayer({ key: videoSrc, state: "error", time: 0, duration: 0, message: err?.message || (err ? `media error ${err.code}` : null) });
              }}
            />
            {!videoSrc ? (
              <div className="stage-note">{selectedRows.length === 0 ? "Select a machine video and press Start test" : thermalRow?.selected ? "Press Start test" : "No video selected"}</div>
            ) : view.state === "error" ? (
              <div className="stage-note stage-note--error" role="alert">Video could not be loaded{view.message ? `: ${view.message}` : ""}</div>
            ) : view.state === "loading" || view.state === "buffering" ? (
              <div className="stage-note stage-note--over">{view.state === "loading" ? "Loading video…" : "Buffering…"}</div>
            ) : null}
          </div>
          <div className="timeline">
            <div className="track" role="progressbar" aria-label="Video playback" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progressRatio * 100)}>
              <div className="track-fill" style={{ width: `${progressRatio * 100}%` }} />
            </div>
            <span className="num">{formatDuration(view.time * 1000)} / {view.duration > 0 ? formatDuration(view.duration * 1000) : "--:--"}</span>
          </div>
          {running ? (
            <ul className="feeds">
              {selectedRows.map((row) => {
                const progress = current?.progress[MODALITY[row.key]];
                return (
                  <li key={row.key}>
                    <span className="feeds-name">{INPUT_TITLES[row.key]}</span>
                    <span className="feeds-run">{row.runLabel}</span>
                    <span className="muted num">{row.key === "thermal" && thermalProgress ? `analysed ${describeProgress(thermalProgress)}` : progress ? describeProgress(progress) : "position pending"}</span>
                  </li>
                );
              })}
            </ul>
          ) : null}
        </section>

        {/* OUTPUT */}
        <section className="panel output" aria-labelledby="output-title" aria-live="polite">
          <div className="panel-head">
            <h2 id="output-title">Output</h2>
            <span className="push muted">{lastUpdate && !Number.isNaN(lastUpdate.getTime()) ? `Updated ${lastUpdate.toLocaleTimeString()}` : running ? "Waiting for data" : "Idle"}</span>
          </div>
          {selectedRows.length === 0 ? <p className="muted">No input selected.</p> : null}
          {rows.map((row, index) => {
            if (!row.selected) return null;
            const reading = readings[index];
            const deviation = deriveDeviation(row.key, health, running);
            const thermal = row.key === "thermal" ? current?.thermal : null;
            return (
              <div className="out" key={row.key}>
                <div className="out-head">
                  <span className="out-name">{INPUT_TITLES[row.key]}</span>
                  {(reading.kind === "value" || reading.kind === "unavailable") && reading.version ? <span className="tag">{reading.version}</span> : null}
                </div>
                <div className="out-main">
                  {reading.kind === "value" ? <strong className={`pill pill--${toneFor(row.key, reading.label)}`}>{reading.label}</strong>
                    : reading.kind === "unavailable" ? (reading.guess
                      ? <><span className="out-tent">{reading.guess}</span><span className="muted"> best guess &middot; low confidence</span></>
                      : <span className="out-na">{reading.reason}</span>)
                    : reading.kind === "waiting" ? <span className="muted">Waiting for first result&hellip;</span>
                    : <span className="muted">{running ? "Waiting…" : "–"}</span>}
                  {reading.kind === "value" && reading.detail ? <span className="muted"> {reading.detail}</span> : null}
                </div>
                <div className="out-meta muted">
                  {(reading.kind === "value" || reading.kind === "unavailable") && reading.confidence !== null
                    ? `Confidence ${percent(reading.confidence)}${reading.reliability ? ` (${reading.reliability})` : ""}`
                    : reading.kind === "value" ? "Confidence not provided" : ""}
                  {row.known ? `${reading.kind === "value" || reading.kind === "unavailable" ? " · " : ""}Run label: ${row.known}` : ""}
                </div>
                {thermal ? (
                  <div className="out-meta muted num">Heat intensity (relative 0&ndash;255, not &deg;C): mean {thermal.mean_intensity.toFixed(1)} &middot; peak {thermal.max_intensity.toFixed(0)} &middot; hotspot {(thermal.hotspot_area_fraction * 100).toFixed(1)}% of frame</div>
                ) : null}
                {row.key === "thermal" && (reading.kind === "value" || reading.kind === "unavailable") ? <div className="out-meta muted">Class from the induction-motor image classifier; not evaluated on video.</div> : null}
                {deviation ? <div className="out-meta muted">{deviation}</div> : null}
              </div>
            );
          })}

          {single ? (
            <div className="out">
              <div className="out-head"><span className="out-name">Status and events</span></div>
              <div className="out-main out-main--s">
                {health ? <><strong className={`pill pill--${healthTone(health.status)}`}>{capitalise(health.status)}</strong>{health.health_score !== null ? <span className="muted"> score {Math.round(health.health_score)}/100</span> : null}</> : <span className="muted">{running ? "Waiting…" : "–"}</span>}
              </div>
              {eventLog.length > 0 ? (
                <ul className="events">
                  {eventLog.map((event, i) => (
                    <li key={`${event.at}-${event.type}-${i}`} className={eventTone(event)}>
                      <span className="muted num">{new Date(event.at).toLocaleTimeString()}</span>{" "}
                      {event.type === "event_started" ? `Anomaly started${event.status ? ` (${event.status})` : ""}` : event.type === "event_cleared" ? "Anomaly cleared" : event.type}
                    </li>
                  ))}
                </ul>
              ) : running && health ? <div className="out-meta muted">No events</div> : null}
            </div>
          ) : selectedRows.length > 1 ? (
            <p className="muted out-foot">Results are per input; the recordings are not synchronized, so there is no combined result.</p>
          ) : null}
        </section>
      </main>

      <ModelResults />
    </div>
  );
}
