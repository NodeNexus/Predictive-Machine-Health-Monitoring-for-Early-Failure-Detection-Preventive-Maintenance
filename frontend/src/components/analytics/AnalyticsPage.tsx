import type { DemoStatus, Machine, MachineHealthState, MachineVideoEntry, MLReliability, TelemetryPayload, TelemetrySeriesPoint } from "../../types";
import { BandEnergyChart, MfccChart, SignalTrendChart, SpectralPeaksChart } from "../charts/TelemetryCharts";
import { DataState } from "../common/DataState";
import { MetricValue } from "../common/MetricValue";
import { Panel } from "../common/Panel";
import { SectionHeading } from "../common/SectionHeading";
import { StatusBadge, type SurfaceStatus } from "../common/StatusBadge";
import { ThermalVideoFeed } from "../thermal/ThermalVideoFeed";

type Modality = "thermal" | "vibration" | "acoustic";

interface Props {
  modality: Modality;
  machine: Machine | null;
  health: MachineHealthState | null;
  latest: TelemetryPayload | null;
  telemetrySeries: TelemetrySeriesPoint[];
  telemetryStatus: SurfaceStatus;
  lastMessageAt: number | null;
  machineVideos: MachineVideoEntry[];
  demoStatus: DemoStatus | null;
}

function number(value: number | null | undefined, digits = 2) {
  return typeof value === "number" && Number.isFinite(value) ? value.toLocaleString(undefined, { maximumFractionDigits: digits }) : "—";
}

function shortTime(value: string | number | null) {
  if (!value) return "No envelope received";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Time unavailable" : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function modalityStatus(latest: TelemetryPayload | null, modality: Modality) {
  if (!latest) return { status: "awaiting", label: "Awaiting envelope" };
  return latest[modality]
    ? { status: "live", label: "Snapshot present" }
    : { status: "missing_data", label: "Missing in latest envelope" };
}

function ModalityEvidence({ health, modality }: { health: MachineHealthState | null; modality: Modality }) {
  const evidence = health?.evidence.filter((item) => item.modality === modality) ?? [];
  return (
    <Panel tone="ink" className="modality-evidence-panel">
      <div className="panel-title-row"><div><div className="panel-kicker">Backend evidence</div><h2>{modality} observations</h2></div><span className="panel-title-row__hint">{evidence.length} reported</span></div>
      {evidence.length === 0 ? (
        <DataState tone="empty" title="No evidence items reported" description="Evidence is supplied by the fusion response after the backend has a qualified observation." compact />
      ) : (
        <div className="evidence-list">
          {evidence.map((item, index) => (
            <div className="evidence-row" key={`${item.modality}-${item.feature}-${index}`}>
              <div><strong>{item.feature}</strong><span>{item.note ?? "Backend evidence item"}</span></div>
              <div><strong>{number(item.value, 3)}</strong><span>Value</span></div>
              <div><strong>{number(item.deviation, 2)}</strong><span>Deviation</span></div>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

interface ModalityMLProps {
  prediction: string | null | undefined;
  confidence: number | null | undefined;
  reliability: MLReliability | null | undefined;
  modelVersion: string | null | undefined;
  limitation: string;
  extra?: { label: string; value: string | null }[];
}

/** Individual modality's own ML V1 confidence-gate output - deliberately a
 * SEPARATE panel from the deterministic feature snapshot above it. A `null`
 * prediction with a `low`/`unavailable` reliability means the confidence
 * gate suppressed the reading (or the model produced none) - it is never
 * rendered as a definitive class. */
function ModalityMLPanel({ prediction, confidence, reliability, modelVersion, limitation, extra }: ModalityMLProps) {
  const suppressed = reliability === "low" || reliability === "unavailable" || reliability == null;
  const badgeStatus = reliability === "high" ? "normal" : reliability === "low" ? "warning" : "unknown";
  const badgeLabel = reliability === "high" ? "High confidence" : reliability === "low" ? "Suppressed (low confidence)" : "Unavailable";
  return (
    <Panel tone="ink" className="modality-ml-panel">
      <div className="panel-title-row">
        <div><div className="panel-kicker">Machine learning evidence (V1)</div><h2>Confidence-gated ML output</h2></div>
        <StatusBadge status={badgeStatus} label={badgeLabel} />
      </div>
      <div className="metric-grid metric-grid--dense">
        <MetricValue label="Prediction" value={suppressed ? "Uncertain" : (prediction ?? null)} tone={suppressed ? "muted" : "default"} />
        <MetricValue label="Confidence" value={confidence != null ? confidence * 100 : null} unit="%" format={(value) => value.toFixed(1)} hint="Raw confidence, preserved even when suppressed" />
        <MetricValue label="Model version" value={modelVersion ?? null} />
        {extra?.map((item) => <MetricValue key={item.label} label={item.label} value={item.value} />)}
      </div>
      <p className="chart-note">
        {suppressed
          ? "This modality's ML confidence gate suppressed the prediction (or the model has not produced a reading yet) - a suppressed reading is never shown as a definitive class."
          : "This is a single modality's own ML V1 output, not the deterministic machine health above."}
        {" "}
        {limitation}
      </p>
    </Panel>
  );
}

export function AnalyticsPage({ modality, machine, health, latest, telemetrySeries, telemetryStatus, lastMessageAt, machineVideos, demoStatus }: Props) {
  const title = modality[0].toUpperCase() + modality.slice(1);
  const current = latest?.[modality] ?? null;
  const connection = modalityStatus(latest, modality);
  const confidence = typeof health?.confidence === "number" ? `${Math.round(health.confidence * 100)}%` : "Not reported";

  if (!machine) {
    return (
      <div className="page modality-page">
        <SectionHeading eyebrow={`${title} analysis`} title={title} description="Select a machine to inspect its backend measurements." />
        <Panel tone="ink"><DataState tone="empty" title="No machine selected" description="Choose a machine from the top bar or register an asset in Machines." /></Panel>
      </div>
    );
  }

  const latestMode = latest?.mode === "demo" ? "Dataset telemetry" : latest?.mode === "live" ? "Live telemetry" : "No mode reported";
  return (
    <div className={`page modality-page modality-page--${modality}`}>
      <SectionHeading
        eyebrow={`${title} signal analysis`}
        title={machine.machine_name}
        description={modality === "thermal"
          ? "Relative intensity, hotspot, and gradient measurements returned by the thermal pipeline. No image frame or calibrated temperature is included."
          : modality === "vibration"
            ? "Time-domain and spectral features returned by the vibration analyzer. The UI does not generate a waveform or anomaly score."
            : "Acoustic spectral, band-energy, and MFCC features returned by the analyzer. No spectrogram matrix is included in telemetry."}
        action={<div className="heading-actions"><StatusBadge status={connection.status} label={connection.label} /><StatusBadge status={telemetryStatus} label={`WS ${telemetryStatus === "connected" ? "receiving" : telemetryStatus}`} /></div>}
      />

      <div className="modality-context-strip">
        <div><span>Machine ID</span><code>{machine.machine_id}</code></div>
        <div><span>Health state</span><StatusBadge status={health?.status ?? "unknown"} label={(health?.status ?? "unknown").toUpperCase()} /></div>
        <div><span>Evidence coverage</span><strong>{confidence}</strong></div>
        <div><span>Telemetry mode</span><strong>{latestMode}</strong></div>
        <div><span>Last envelope</span><strong>{shortTime(lastMessageAt)}</strong></div>
      </div>

      {modality === "thermal" ? <ThermalView data={current && "mean_intensity" in current ? current : null} samples={telemetrySeries} machineVideos={machineVideos} demoStatus={demoStatus} /> : null}
      {modality === "vibration" ? <VibrationView data={current && "rms" in current && "analysis_type" in current ? current : null} samples={telemetrySeries} /> : null}
      {modality === "acoustic" ? <AcousticView data={current && "rms" in current && "spectral_rolloff" in current ? current : null} samples={telemetrySeries} /> : null}

      <ModalityEvidence health={health} modality={modality} />
    </div>
  );
}

function ThermalView({ data, samples, machineVideos, demoStatus }: { data: TelemetryPayload["thermal"]; samples: TelemetrySeriesPoint[]; machineVideos: MachineVideoEntry[]; demoStatus: DemoStatus | null }) {
  const seriesData = samples.flatMap((sample) => sample.thermal ? [{ timestamp: sample.timestamp, mean: sample.thermal.mean_intensity, maximum: sample.thermal.max_intensity }] : []);
  const areaData = samples.flatMap((sample) => sample.thermal ? [{ timestamp: sample.timestamp, area: sample.thermal.hotspot_area_fraction * 100 }] : []);
  const activeThermalPath = demoStatus?.sources?.thermal ?? null;
  const activeVideo = activeThermalPath ? machineVideos.find((entry) => entry.path === activeThermalPath) ?? null : null;
  return (
    <div className="modality-view modality-view--thermal">
      <ThermalVideoFeed className="thermal-feed-panel--full" activeVideo={activeVideo} sessionRunning={Boolean(demoStatus?.running)} thermal={data} />
      <Panel tone="ink" className="modality-metrics-panel">
        <div className="panel-title-row"><div><div className="panel-kicker">Thermal feature snapshot</div><h2>Intensity and hotspot measures</h2></div><StatusBadge status={data ? "live" : "missing_data"} label={data ? "Snapshot present" : "No snapshot"} /></div>
        {!data ? <DataState tone="unavailable" title="Thermal features unavailable" description="No thermal feature block is present in the selected machine's latest telemetry envelope." compact /> : null}
        <div className="metric-grid metric-grid--dense">
          <MetricValue label="Std intensity" value={data?.std_intensity} format={(value) => number(value)} />
          <MetricValue label="Hotspot pixels" value={data?.hotspot_pixel_count} />
          <MetricValue label="Gradient mean" value={data?.gradient_mean} format={(value) => number(value)} />
          <MetricValue label="Gradient max" value={data?.gradient_max} format={(value) => number(value)} />
          <MetricValue label="Hotspot centroid X" value={data?.hotspot_centroid_x} unit="px" format={(value) => number(value, 1)} />
          <MetricValue label="Hotspot centroid Y" value={data?.hotspot_centroid_y} unit="px" format={(value) => number(value, 1)} />
        </div>
        <p className="chart-note">Mean, max, min, hotspot threshold, hotspot area, and ΔT are shown once, in the Thermal Feed card above.</p>
        {data ? <p className="chart-note">{data.is_radiometric ? "Radiometric flag reported, but no temperature conversion field is supplied." : "Non-radiometric source; values are relative grayscale intensity, not °C."} Source: <span title={data.source}>{data.source}</span></p> : null}
      </Panel>
      <ModalityMLPanel
        prediction={data?.ml_prediction}
        confidence={data?.ml_confidence}
        reliability={data?.ml_reliability}
        modelVersion={data?.model_version}
        extra={[
          { label: "Condition context", value: data?.ml_condition ?? null },
          { label: "Load context", value: data?.ml_load_context ?? null },
        ]}
        limitation="Known limitation: load-level confusion is significant (CFL<->CML, HML->HFL) - confidence does not reliably separate this error mode."
      />
      <SignalTrendChart title="Mean and maximum intensity" data={seriesData} series={[{ key: "mean", label: "Mean intensity", color: "#1D74C9" }, { key: "maximum", label: "Maximum intensity", color: "#B45309" }]} unit="intensity" height={205} emptyTitle="Waiting for thermal samples" emptyDescription="The WebSocket has not supplied a thermal feature block for this machine." />
      <SignalTrendChart title="Hotspot area fraction" data={areaData} series={[{ key: "area", label: "Hotspot area", color: "#0D9488" }]} unit="%" height={180} emptyTitle="No hotspot history" emptyDescription="Hotspot area will appear after thermal feature samples arrive." />
    </div>
  );
}

function VibrationView({ data, samples }: { data: TelemetryPayload["vibration"]; samples: TelemetrySeriesPoint[] }) {
  const seriesData = samples.flatMap((sample) => sample.vibration ? [{ timestamp: sample.timestamp, rms: sample.vibration.rms }] : []);
  return (
    <div className="modality-view modality-view--vibration">
      <Panel tone="ink" className="modality-metrics-panel">
        <div className="panel-title-row"><div><div className="panel-kicker">Vibration feature snapshot</div><h2>Time-domain and spectral metrics</h2></div><StatusBadge status={data ? "live" : "missing_data"} label={data ? "Snapshot present" : "No snapshot"} /></div>
        {!data ? <DataState tone="unavailable" title="Vibration features unavailable" description="No vibration feature block is present in the selected machine's latest telemetry envelope." compact /> : null}
        <div className="metric-grid metric-grid--dense">
          <MetricValue label="RMS" value={data?.rms} format={(value) => number(value, 4)} />
          <MetricValue label="Variance" value={data?.variance} format={(value) => number(value, 4)} />
          <MetricValue label="Std deviation" value={data?.std} format={(value) => number(value, 4)} />
          <MetricValue label="Peak" value={data?.peak} format={(value) => number(value, 4)} />
          <MetricValue label="Peak-to-peak" value={data?.peak_to_peak} format={(value) => number(value, 4)} />
          <MetricValue label="Crest factor" value={data?.crest_factor} format={(value) => number(value, 3)} />
          <MetricValue label="Kurtosis" value={data?.kurtosis} format={(value) => number(value, 3)} />
          <MetricValue label="Skewness" value={data?.skewness} format={(value) => number(value, 3)} />
          <MetricValue label="Dominant frequency" value={data?.dominant_frequency} unit="Hz" format={(value) => number(value, 1)} />
          <MetricValue label="Spectral centroid" value={data?.spectral_centroid} unit="Hz" format={(value) => number(value, 1)} />
          <MetricValue label="Spectral bandwidth" value={data?.spectral_bandwidth} unit="Hz" format={(value) => number(value, 1)} />
          <MetricValue label="Analysis type" value={data?.analysis_type === "bearing_specific" ? "Bearing specific" : data ? "Generic spectral" : null} />
        </div>
        {data ? <p className="chart-note">Source: <span title={data.source}>{data.source}</span>{data.bearing_fault_frequencies ? " · Bearing frequencies reported" : " · Bearing frequencies not reported"}</p> : null}
      </Panel>
      <ModalityMLPanel
        prediction={data?.ml_prediction}
        confidence={data?.ml_confidence}
        reliability={data?.ml_reliability}
        modelVersion={data?.ml_model_version}
        limitation="Known limitation: labels are project-derived from the IMS degradation trajectory (RMS and kurtosis participate in both the input features and the label rule) - a derived-label trajectory classifier, NOT an independently validated fault detector."
      />
      <SignalTrendChart title="Vibration RMS history" data={seriesData} series={[{ key: "rms", label: "RMS", color: "#1D74C9" }]} unit="RMS" height={205} emptyTitle="Waiting for vibration samples" emptyDescription="The WebSocket has not supplied vibration features for this machine." />
      <SpectralPeaksChart peaks={data?.spectral_peaks} title="Spectral peaks" color="#1D74C9" height={205} />
      <BandEnergyChart data={data?.band_energies} title="Band energy" description={data?.band_energies ? `${data.band_energies.band_type.replace("_", "-")} frequency bands.` : "No band-energy array was reported."} color="#0D9488" height={205} />
    </div>
  );
}

function AcousticView({ data, samples }: { data: TelemetryPayload["acoustic"]; samples: TelemetrySeriesPoint[] }) {
  const seriesData = samples.flatMap((sample) => sample.acoustic ? [{ timestamp: sample.timestamp, rms: sample.acoustic.rms }] : []);
  return (
    <div className="modality-view modality-view--acoustic">
      <Panel tone="ink" className="modality-metrics-panel">
        <div className="panel-title-row"><div><div className="panel-kicker">Acoustic feature snapshot</div><h2>Amplitude and spectral metrics</h2></div><StatusBadge status={data ? "live" : "missing_data"} label={data ? "Snapshot present" : "No snapshot"} /></div>
        {!data ? <DataState tone="unavailable" title="Acoustic features unavailable" description="No acoustic feature block is present in the selected machine's latest telemetry envelope." compact /> : null}
        <div className="metric-grid metric-grid--dense">
          <MetricValue label="RMS" value={data?.rms} format={(value) => number(value, 4)} />
          <MetricValue label="Peak amplitude" value={data?.peak_amplitude} format={(value) => number(value, 4)} />
          <MetricValue label="Crest factor" value={data?.crest_factor} format={(value) => number(value, 3)} />
          <MetricValue label="Energy" value={data?.energy} format={(value) => number(value, 4)} />
          <MetricValue label="Dominant frequency" value={data?.dominant_frequency} unit="Hz" format={(value) => number(value, 1)} />
          <MetricValue label="Spectral centroid" value={data?.spectral_centroid} unit="Hz" format={(value) => number(value, 1)} />
          <MetricValue label="Spectral bandwidth" value={data?.spectral_bandwidth} unit="Hz" format={(value) => number(value, 1)} />
          <MetricValue label="Spectral rolloff" value={data?.spectral_rolloff} unit="Hz" format={(value) => number(value, 1)} />
          <MetricValue label="Spectral flatness" value={data?.spectral_flatness} format={(value) => number(value, 4)} />
        </div>
        {data ? <p className="chart-note">Source: <span title={data.source}>{data.source}</span></p> : null}
      </Panel>
      <ModalityMLPanel
        prediction={data?.ml_prediction}
        confidence={data?.ml_confidence}
        reliability={data?.ml_reliability}
        modelVersion={data?.ml_model_version}
        limitation="Known limitation: measured test performance varies across recording section/domain groups (macro-F1 0.789-0.965) - a high reading reflects local confidence only, not proven cross-section generalization."
      />
      <SignalTrendChart title="Acoustic RMS history" data={seriesData} series={[{ key: "rms", label: "RMS", color: "#B45309" }]} unit="RMS" height={205} emptyTitle="Waiting for acoustic samples" emptyDescription="The WebSocket has not supplied acoustic features for this machine." />
      <SpectralPeaksChart peaks={data?.spectral_peaks} title="Frequency peaks" color="#B45309" height={205} />
      <BandEnergyChart data={data?.band_energies} title="Octave-band energy" description="Frequency-band energy returned by the acoustic analyzer." color="#0D9488" height={205} />
      <MfccChart mfcc={data?.mfcc} title="MFCC coefficients" color="#1D74C9" height={205} />
    </div>
  );
}
