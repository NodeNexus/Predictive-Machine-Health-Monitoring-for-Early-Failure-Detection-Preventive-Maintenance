import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { AnalyticsPage } from "./components/analytics/AnalyticsPage";
import { DatasetsPage } from "./components/datasets/DatasetsPage";
import { DemoConsole } from "./components/demo/DemoConsole";
import { DevicesPage } from "./components/devices/DevicesPage";
import { EventsPage } from "./components/events/EventsPage";
import { AppShell, type AppSection } from "./components/layout/AppShell";
import { MachinesPage } from "./components/machines/MachinesPage";
import { OverviewPage } from "./components/overview/OverviewPage";
import { api, isAbortError, isApiError } from "./services/api";
import { useTelemetry, type ConnectionState } from "./services/useTelemetry";
import type {
  AnomalyEventRecord,
  DatasetInfo,
  DemoStartRequest,
  DemoStatus,
  DeviceStatus,
  HealthHistoryPoint,
  Machine,
  MachineCreate,
  MachineHealthState,
  MachineVideoEntry,
  TelemetrySeriesPoint,
} from "./types";
import type { SurfaceStatus } from "./components/common/StatusBadge";

type RequestState = "idle" | "loading" | "ready" | "error";

function errorMessage(error: unknown) {
  if (isApiError(error)) return error.detail ?? error.message;
  return error instanceof Error ? error.message : "The backend could not be reached.";
}

function telemetrySurfaceStatus(connection: ConnectionState, lastMessageAt: number | null): SurfaceStatus {
  if (connection === "connecting") return "connecting";
  if (connection === "reconnecting") return "reconnecting";
  if (connection === "error") return "error";
  if (connection === "closed") return "offline";
  if (lastMessageAt === null) return "awaiting";
  if (Date.now() - lastMessageAt > 7000) return "stale";
  return "connected";
}

function chronological(points: HealthHistoryPoint[]) {
  return [...points].sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp));
}

function telemetryProjection(incoming: NonNullable<ReturnType<typeof useTelemetry>["latest"]>): TelemetrySeriesPoint {
  return {
    timestamp: incoming.timestamp,
    mode: incoming.mode,
    thermal: incoming.thermal ? {
      mean_intensity: incoming.thermal.mean_intensity,
      max_intensity: incoming.thermal.max_intensity,
      hotspot_area_fraction: incoming.thermal.hotspot_area_fraction,
      gradient_mean: incoming.thermal.gradient_mean,
    } : null,
    vibration: incoming.vibration ? {
      rms: incoming.vibration.rms,
      dominant_frequency: incoming.vibration.dominant_frequency,
      crest_factor: incoming.vibration.crest_factor,
    } : null,
    acoustic: incoming.acoustic ? {
      rms: incoming.acoustic.rms,
      dominant_frequency: incoming.acoustic.dominant_frequency,
      spectral_centroid: incoming.acoustic.spectral_centroid,
    } : null,
  };
}

function App() {
  const [section, setSection] = useState<AppSection>("fusion");
  const [apiState, setApiState] = useState<RequestState>("loading");
  const [apiError, setApiError] = useState<string | null>(null);
  const [machines, setMachines] = useState<Machine[]>([]);
  const [devices, setDevices] = useState<DeviceStatus[]>([]);
  const [datasets, setDatasets] = useState<DatasetInfo[]>([]);
  const [machineVideos, setMachineVideos] = useState<MachineVideoEntry[]>([]);
  const [machineVideosState, setMachineVideosState] = useState<RequestState>("loading");
  const [machineVideosError, setMachineVideosError] = useState<string | null>(null);
  const [selectedMachineId, setSelectedMachineId] = useState<string | null>(null);
  const [health, setHealth] = useState<MachineHealthState | null>(null);
  const [history, setHistory] = useState<HealthHistoryPoint[]>([]);
  const [telemetrySeries, setTelemetrySeries] = useState<TelemetrySeriesPoint[]>([]);
  const [events, setEvents] = useState<AnomalyEventRecord[]>([]);
  const [detailState, setDetailState] = useState<RequestState>("idle");
  const [detailError, setDetailError] = useState<string | null>(null);
  const [devicesState, setDevicesState] = useState<RequestState>("loading");
  const [devicesError, setDevicesError] = useState<string | null>(null);
  const [datasetsState, setDatasetsState] = useState<RequestState>("loading");
  const [datasetsError, setDatasetsError] = useState<string | null>(null);
  const [demoStatus, setDemoStatus] = useState<DemoStatus | null>(null);
  const [demoState, setDemoState] = useState<RequestState>("loading");
  const [demoError, setDemoError] = useState<string | null>(null);
  const [demoActionPending, setDemoActionPending] = useState(false);
  const detailRequestRef = useRef(0);
  const eventsRequestRef = useRef(0);

  const telemetry = useTelemetry({ machineId: selectedMachineId, enabled: true, reconnect: true });
  const selectedMachine = useMemo(
    () => machines.find((machine) => machine.machine_id === selectedMachineId) ?? null,
    [machines, selectedMachineId],
  );
  const telemetryStatus = telemetrySurfaceStatus(telemetry.connection, telemetry.lastMessageAt);
  const apiStatus: SurfaceStatus = apiState === "ready" ? "connected" : apiState === "error" ? "error" : "connecting";

  const refreshFleet = useCallback(async () => {
    setApiState("loading");
    setApiError(null);
    const results = await Promise.allSettled([
      api.health({ timeoutMs: 8000 }),
      api.listMachines({ timeoutMs: 8000 }),
      api.listDevices({ timeoutMs: 15000 }),
      api.listDatasets({ timeoutMs: 8000 }),
      api.machineVideos({ timeoutMs: 8000 }),
    ]);
    const [healthResult, machineResult, devicesResult, datasetsResult, machineVideosResult] = results;
    if (healthResult.status === "fulfilled") setApiState("ready");
    else { setApiState("error"); setApiError(errorMessage(healthResult.reason)); }
    if (machineResult.status === "fulfilled") {
      setMachines(machineResult.value);
      setSelectedMachineId((current) => current && machineResult.value.some((machine) => machine.machine_id === current) ? current : machineResult.value[0]?.machine_id ?? null);
    } else setApiError((current) => current ?? errorMessage(machineResult.reason));
    if (devicesResult.status === "fulfilled") { setDevices(devicesResult.value); setDevicesState("ready"); setDevicesError(null); }
    else { setDevicesState("error"); setDevicesError(errorMessage(devicesResult.reason)); }
    if (datasetsResult.status === "fulfilled") { setDatasets(datasetsResult.value); setDatasetsState("ready"); setDatasetsError(null); }
    else { setDatasetsState("error"); setDatasetsError(errorMessage(datasetsResult.reason)); }
    if (machineVideosResult.status === "fulfilled") { setMachineVideos(machineVideosResult.value); setMachineVideosState("ready"); setMachineVideosError(null); }
    else { setMachineVideosState("error"); setMachineVideosError(errorMessage(machineVideosResult.reason)); }
  }, []);

  const refreshDemoStatus = useCallback(async () => {
    try {
      const next = await api.demoStatus({ timeoutMs: 8000 });
      setDemoStatus(next);
      setDemoState("ready");
      setDemoError(null);
    } catch (error) {
      if (isAbortError(error)) return;
      setDemoState("error");
      setDemoError(errorMessage(error));
    }
  }, []);

  const refreshEvents = useCallback(async (machineId: string) => {
    const requestId = eventsRequestRef.current + 1;
    eventsRequestRef.current = requestId;
    try {
      const next = await api.machineEvents(machineId, { limit: 100, timeoutMs: 10000 });
      if (eventsRequestRef.current === requestId) setEvents(next);
    } catch {
      if (eventsRequestRef.current === requestId) setEvents([]);
    }
  }, []);

  const refreshDetails = useCallback(async (machineId: string) => {
    const requestId = detailRequestRef.current + 1;
    detailRequestRef.current = requestId;
    const eventsRequestId = eventsRequestRef.current + 1;
    eventsRequestRef.current = eventsRequestId;
    setDetailState("loading");
    setDetailError(null);
    const results = await Promise.allSettled([
      api.machineStatus(machineId, { timeoutMs: 8000 }),
      api.machineHistory(machineId, { limit: 240, timeoutMs: 10000 }),
      api.machineEvents(machineId, { limit: 100, timeoutMs: 10000 }),
    ]);
    if (detailRequestRef.current !== requestId) return;
    const [healthResult, historyResult, eventsResult] = results;
    if (healthResult.status === "fulfilled") setHealth(healthResult.value);
    if (historyResult.status === "fulfilled") {
      const fetched = chronological(historyResult.value);
      setHistory((current) => {
        const merged = new Map<string, HealthHistoryPoint>();
        for (const point of [...fetched, ...current]) merged.set(point.timestamp, point);
        return chronological([...merged.values()]).slice(-240);
      });
    }
    if (eventsResult.status === "fulfilled" && eventsRequestRef.current === eventsRequestId) setEvents(eventsResult.value);
    if (healthResult.status === "rejected" && historyResult.status === "rejected" && eventsResult.status === "rejected") {
      setDetailState("error");
      setDetailError(errorMessage(healthResult.reason));
    } else setDetailState("ready");
  }, []);

  useEffect(() => {
    void refreshFleet();
    void refreshDemoStatus();
    const interval = window.setInterval(() => void refreshDemoStatus(), 5000);
    return () => window.clearInterval(interval);
  }, [refreshDemoStatus, refreshFleet]);

  useEffect(() => {
    detailRequestRef.current += 1;
    eventsRequestRef.current += 1;
    setHealth(null);
    setHistory([]);
    setTelemetrySeries([]);
    setEvents([]);
    setDetailError(null);
    if (!selectedMachineId) { setDetailState("idle"); return; }
    void refreshDetails(selectedMachineId);
  }, [refreshDetails, selectedMachineId]);

  useEffect(() => {
    const incoming = telemetry.latest;
    if (!incoming || !selectedMachineId || incoming.machine_id !== selectedMachineId) return;
    const incomingHealth = incoming.health;
    if (incomingHealth) {
      setHealth((current) => !current || Date.parse(current.timestamp) <= Date.parse(incomingHealth.timestamp) ? incomingHealth : current);
      setHistory((current) => {
        const next = current.filter((point) => point.timestamp !== incomingHealth.timestamp);
        next.push({ timestamp: incomingHealth.timestamp, health_score: incomingHealth.health_score, status: incomingHealth.status, confidence: incomingHealth.confidence });
        return chronological(next).slice(-240);
      });
    }
    const projection = telemetryProjection(incoming);
    setTelemetrySeries((current) => {
      const next = current.filter((point) => point.timestamp !== projection.timestamp);
      next.push(projection);
      return next.sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp)).slice(-240);
    });
    if (incoming.events.some((event) => event.type === "event_started" || event.type === "event_cleared")) {
      void refreshEvents(selectedMachineId);
    }
  }, [refreshEvents, selectedMachineId, telemetry.latest]);

  const createMachine = useCallback(async (input: MachineCreate) => {
    const created = await api.createMachine(input, { timeoutMs: 8000 });
    setMachines((current) => [...current, created]);
    setSelectedMachineId(created.machine_id);
    setSection("fusion");
  }, []);

  const startDemo = useCallback(async (request: DemoStartRequest) => {
    setDemoError(null);
    setDemoActionPending(true);
    try {
      const next = await api.startDemo(request, { timeoutMs: 10000 });
      setDemoStatus(next);
      setDemoState("ready");
      setSelectedMachineId(request.machine_id);
    } catch (error) {
      setDemoError(errorMessage(error));
      throw error;
    } finally { setDemoActionPending(false); }
  }, []);

  const stopDemo = useCallback(async () => {
    setDemoError(null);
    setDemoActionPending(true);
    try {
      const next = await api.stopDemo({ timeoutMs: 10000 });
      setDemoStatus(next);
      setDemoState("ready");
    } catch (error) {
      setDemoError(errorMessage(error));
      throw error;
    } finally { setDemoActionPending(false); }
  }, []);

  const navigate = useCallback((next: AppSection) => setSection(next), []);
  let content: ReactNode = null;

  if (section === "fusion") content = <OverviewPage machine={selectedMachine} health={health} latest={telemetry.latest} history={history} datasets={datasets} machineVideos={machineVideos} lastMessageAt={telemetry.lastMessageAt} demoStatus={demoStatus} demoStatusState={demoState} demoError={demoError} demoActionPending={demoActionPending} onStartDemo={startDemo} onStopDemo={stopDemo} onNavigate={navigate} />;
  if (section === "machines") content = <MachinesPage machines={machines} selectedMachineId={selectedMachineId} onSelect={setSelectedMachineId} onCreate={createMachine} loading={apiState === "loading"} error={apiError} />;
  if (section === "thermal" || section === "vibration" || section === "acoustic") content = <AnalyticsPage modality={section} machine={selectedMachine} health={health} latest={telemetry.latest} telemetrySeries={telemetrySeries} telemetryStatus={telemetryStatus} lastMessageAt={telemetry.lastMessageAt} machineVideos={machineVideos} demoStatus={demoStatus} />;
  if (section === "events") content = <EventsPage events={events} machineName={selectedMachine?.machine_name} loading={detailState === "loading"} error={detailState === "error" ? detailError : null} onRefresh={selectedMachineId ? () => void refreshEvents(selectedMachineId) : undefined} />;
  if (section === "datasets") content = <DatasetsPage datasets={datasets} loading={datasetsState === "loading"} error={datasetsError} onRefresh={() => { setDatasetsState("loading"); void api.listDatasets({ timeoutMs: 8000 }).then((value) => { setDatasets(value); setDatasetsState("ready"); setDatasetsError(null); }).catch((error) => { setDatasetsState("error"); setDatasetsError(errorMessage(error)); }); }} />;
  if (section === "devices") content = <DevicesPage devices={devices} loading={devicesState === "loading"} error={devicesError} onRefresh={() => { setDevicesState("loading"); void api.listDevices({ timeoutMs: 15000 }).then((value) => { setDevices(value); setDevicesState("ready"); setDevicesError(null); }).catch((error) => { setDevicesState("error"); setDevicesError(errorMessage(error)); }); }} />;
  if (section === "demo") content = <DemoConsole key={selectedMachineId ?? "no-machine"} machines={machines} datasets={datasets} machineVideos={machineVideos} machineVideosLoading={machineVideosState === "loading"} machineVideosError={machineVideosError} selectedMachineId={selectedMachineId} status={demoStatus} loading={demoState === "loading"} error={demoError} onStart={startDemo} onStop={stopDemo} />;

  return (
    <AppShell
      section={section}
      onSectionChange={navigate}
      machines={machines}
      selectedMachineId={selectedMachineId}
      onMachineChange={setSelectedMachineId}
      apiStatus={apiStatus}
      telemetryStatus={telemetryStatus}
      telemetryLabel={telemetryStatus === "awaiting" ? "Awaiting envelope" : telemetryStatus === "connected" ? "Envelope received" : undefined}
      demoStatus={demoStatus}
      demoStatusState={demoState === "ready" ? "ready" : demoState === "error" ? "error" : "loading"}
      dataMode={telemetry.latest?.mode ?? null}
    >
      {content}
    </AppShell>
  );
}

export default App;
