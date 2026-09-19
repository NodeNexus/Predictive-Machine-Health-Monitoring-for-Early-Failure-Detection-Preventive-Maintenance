import type {
  AcousticTelemetry,
  AnomalyEventRecord,
  BandAnalysisResult,
  BandEnergy,
  BearingFaultFrequencies,
  DatasetInfo,
  DemoScenario,
  DemoStatus,
  DeviceConnectionStatus,
  DeviceStatus,
  EvidenceItem,
  FusionModalityEvidence,
  HealthHistoryPoint,
  HealthResponse,
  HealthStatus,
  JsonObject,
  Machine,
  MachineHealthState,
  MachineVideoEntry,
  MLFusionReliability,
  MLFusionTelemetry,
  MLReliability,
  Modality,
  SpectralPeak,
  TelemetryEvent,
  TelemetryPayload,
  ThermalFeedEntry,
  ThermalTelemetry,
  VibrationTelemetry,
} from "../types";

/** A response crossed a trust boundary and did not match the documented DTO. */
export class ContractError extends Error {
  readonly name = "ContractError";
  readonly path: string;
  readonly expected: string;
  readonly received: unknown;

  constructor(path: string, expected: string, received: unknown) {
    super(`Invalid response at ${path}: expected ${expected}`);
    this.path = path;
    this.expected = expected;
    this.received = received;
  }
}

export interface SafeParseResult<T> {
  value: T | null;
  error: ContractError | null;
}

function fail(path: string, expected: string, received: unknown): never {
  throw new ContractError(path, expected, received);
}

function record(value: unknown, path: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return fail(path, "an object", value);
  }
  return value as Record<string, unknown>;
}

function stringValue(value: unknown, path: string): string {
  return typeof value === "string" ? value : fail(path, "a string", value);
}

function optionalString(value: unknown, path: string): string | null {
  return value == null ? null : stringValue(value, path);
}

function numberValue(value: unknown, path: string): number {
  return typeof value === "number" && Number.isFinite(value)
    ? value
    : fail(path, "a finite number", value);
}

function optionalNumber(value: unknown, path: string): number | null {
  return value == null ? null : numberValue(value, path);
}

function booleanValue(value: unknown, path: string): boolean {
  return typeof value === "boolean" ? value : fail(path, "a boolean", value);
}

function arrayValue(value: unknown, path: string): unknown[] {
  return Array.isArray(value) ? value : fail(path, "an array", value);
}

function jsonObject(value: unknown, path: string): JsonObject {
  return record(value, path) as JsonObject;
}

function nullableJsonObject(value: unknown, path: string): JsonObject | null {
  return value == null ? null : jsonObject(value, path);
}

function modalityValue(value: unknown, path: string): Modality {
  if (value === "thermal" || value === "vibration" || value === "acoustic") return value;
  return fail(path, "thermal, vibration, or acoustic", value);
}

function healthStatusValue(value: unknown, path: string): HealthStatus {
  if (value === "normal" || value === "warning" || value === "critical" || value === "unknown") return value;
  return fail(path, "normal, warning, critical, or unknown", value);
}

function deviceStatusValue(value: unknown, path: string): DeviceConnectionStatus {
  if (value === "connected" || value === "not_connected" || value === "error") return value;
  return fail(path, "connected, not_connected, or error", value);
}

function mlReliabilityValue(value: unknown, path: string): MLReliability {
  if (value === "high" || value === "low" || value === "unavailable") return value;
  return fail(path, "high, low, or unavailable", value);
}

/** ML fields are ABSENT (not merged) until a modality's runtime ML model
 * has produced at least one reading, and remain optional forever if the
 * model is unavailable in a given environment - always tolerate a missing
 * key rather than failing the whole envelope. */
function optionalMlReliability(value: unknown, path: string): MLReliability | null {
  return value == null ? null : mlReliabilityValue(value, path);
}

function mlFusionReliabilityValue(value: unknown, path: string): MLFusionReliability {
  if (value === "high" || value === "partial" || value === "unavailable") return value;
  return fail(path, "high, partial, or unavailable", value);
}

function optionalVibrationMlClass(value: unknown, path: string): "healthy" | "degrading" | "severe" | null {
  if (value == null) return null;
  if (value === "healthy" || value === "degrading" || value === "severe") return value;
  return fail(path, "healthy, degrading, severe, or null", value);
}

function optionalAcousticMlClass(value: unknown, path: string): "normal" | "anomaly" | null {
  if (value == null) return null;
  if (value === "normal" || value === "anomaly") return value;
  return fail(path, "normal, anomaly, or null", value);
}

function numberRecord(value: unknown, path: string): Record<string, number> {
  const source = record(value ?? {}, path);
  return Object.fromEntries(Object.entries(source).map(([key, item]) => [key, numberValue(item, `${path}.${key}`)]));
}

function modalityList(value: unknown, path: string): Modality[] {
  return arrayValue(value ?? [], path).map((item, index) => modalityValue(item, `${path}[${index}]`));
}

function parseEvidenceItem(value: unknown, path: string): EvidenceItem {
  const source = record(value, path);
  return {
    modality: modalityValue(source.modality, `${path}.modality`),
    feature: stringValue(source.feature, `${path}.feature`),
    value: optionalNumber(source.value, `${path}.value`),
    baseline_mean: optionalNumber(source.baseline_mean, `${path}.baseline_mean`),
    deviation: optionalNumber(source.deviation, `${path}.deviation`),
    note: optionalString(source.note, `${path}.note`),
  };
}

export function parseHealthResponse(value: unknown): HealthResponse {
  const source = record(value, "health");
  return {
    status: stringValue(source.status, "health.status"),
    app: stringValue(source.app, "health.app"),
    environment: stringValue(source.environment, "health.environment"),
  };
}

export function parseMachine(value: unknown): Machine {
  const source = record(value, "machine");
  return {
    machine_id: stringValue(source.machine_id, "machine.machine_id"),
    machine_name: stringValue(source.machine_name, "machine.machine_name"),
    machine_type: optionalString(source.machine_type, "machine.machine_type"),
    manufacturer: optionalString(source.manufacturer, "machine.manufacturer"),
    model: optionalString(source.model, "machine.model"),
    rpm: optionalNumber(source.rpm, "machine.rpm"),
    rated_power: optionalNumber(source.rated_power, "machine.rated_power"),
    location: optionalString(source.location, "machine.location"),
    sensor_configuration: nullableJsonObject(source.sensor_configuration, "machine.sensor_configuration"),
    baseline_status: stringValue(source.baseline_status, "machine.baseline_status"),
    monitoring_status: stringValue(source.monitoring_status, "machine.monitoring_status"),
    created_at: stringValue(source.created_at, "machine.created_at"),
  };
}

export function parseMachineHealthState(value: unknown): MachineHealthState {
  const source = record(value, "health_state");
  return {
    machine_id: stringValue(source.machine_id, "health_state.machine_id"),
    timestamp: stringValue(source.timestamp, "health_state.timestamp"),
    health_score: optionalNumber(source.health_score, "health_state.health_score"),
    status: healthStatusValue(source.status ?? "unknown", "health_state.status"),
    severity: optionalString(source.severity, "health_state.severity"),
    confidence: optionalNumber(source.confidence, "health_state.confidence"),
    modality_contributions: numberRecord(source.modality_contributions, "health_state.modality_contributions"),
    missing_modalities: modalityList(source.missing_modalities, "health_state.missing_modalities"),
    evidence: arrayValue(source.evidence ?? [], "health_state.evidence").map((item, index) =>
      parseEvidenceItem(item, `health_state.evidence[${index}]`),
    ),
    model_version: optionalString(source.model_version, "health_state.model_version"),
  };
}

function parseBandEnergy(value: unknown, path: string): BandEnergy {
  const source = record(value, path);
  return {
    center_frequency: numberValue(source.center_frequency, `${path}.center_frequency`),
    low_frequency: numberValue(source.low_frequency, `${path}.low_frequency`),
    high_frequency: numberValue(source.high_frequency, `${path}.high_frequency`),
    energy: numberValue(source.energy, `${path}.energy`),
  };
}

function parseBandAnalysis(value: unknown, path: string): BandAnalysisResult {
  const source = record(value, path);
  if (source.band_type !== "octave" && source.band_type !== "third_octave") {
    return fail(`${path}.band_type`, "octave or third_octave", source.band_type);
  }
  return {
    band_type: source.band_type,
    bands: arrayValue(source.bands, `${path}.bands`).map((item, index) => parseBandEnergy(item, `${path}.bands[${index}]`)),
  };
}

function parseSpectralPeak(value: unknown, path: string): SpectralPeak {
  const source = record(value, path);
  return {
    frequency: numberValue(source.frequency, `${path}.frequency`),
    magnitude: numberValue(source.magnitude, `${path}.magnitude`),
  };
}

function parseBearingFaultFrequencies(value: unknown, path: string): BearingFaultFrequencies {
  const source = record(value, path);
  return {
    bpfo: numberValue(source.bpfo, `${path}.bpfo`),
    bpfi: numberValue(source.bpfi, `${path}.bpfi`),
    bsf: numberValue(source.bsf, `${path}.bsf`),
    ftf: numberValue(source.ftf, `${path}.ftf`),
  };
}

export function parseVibrationTelemetry(value: unknown): VibrationTelemetry {
  const source = record(value, "telemetry.vibration");
  const analysisType = source.analysis_type;
  if (analysisType !== "generic_spectral" && analysisType !== "bearing_specific") {
    return fail("telemetry.vibration.analysis_type", "generic_spectral or bearing_specific", analysisType);
  }
  return {
    source: stringValue(source.source, "telemetry.vibration.source"),
    rms: numberValue(source.rms, "telemetry.vibration.rms"),
    variance: numberValue(source.variance, "telemetry.vibration.variance"),
    std: numberValue(source.std, "telemetry.vibration.std"),
    peak: numberValue(source.peak, "telemetry.vibration.peak"),
    peak_to_peak: numberValue(source.peak_to_peak, "telemetry.vibration.peak_to_peak"),
    crest_factor: numberValue(source.crest_factor, "telemetry.vibration.crest_factor"),
    kurtosis: numberValue(source.kurtosis, "telemetry.vibration.kurtosis"),
    skewness: numberValue(source.skewness, "telemetry.vibration.skewness"),
    dominant_frequency: numberValue(source.dominant_frequency, "telemetry.vibration.dominant_frequency"),
    spectral_centroid: numberValue(source.spectral_centroid, "telemetry.vibration.spectral_centroid"),
    spectral_bandwidth: numberValue(source.spectral_bandwidth, "telemetry.vibration.spectral_bandwidth"),
    spectral_peaks: arrayValue(source.spectral_peaks, "telemetry.vibration.spectral_peaks").map((item, index) =>
      parseSpectralPeak(item, `telemetry.vibration.spectral_peaks[${index}]`),
    ),
    band_energies:
      source.band_energies == null ? null : parseBandAnalysis(source.band_energies, "telemetry.vibration.band_energies"),
    analysis_type: analysisType,
    bearing_fault_frequencies:
      source.bearing_fault_frequencies == null
        ? null
        : parseBearingFaultFrequencies(source.bearing_fault_frequencies, "telemetry.vibration.bearing_fault_frequencies"),
    ml_prediction: optionalVibrationMlClass(source.ml_prediction, "telemetry.vibration.ml_prediction"),
    ml_confidence: optionalNumber(source.ml_confidence, "telemetry.vibration.ml_confidence"),
    ml_reliability: optionalMlReliability(source.ml_reliability, "telemetry.vibration.ml_reliability"),
    ml_model_version: optionalString(source.ml_model_version, "telemetry.vibration.ml_model_version"),
  };
}

export function parseAcousticTelemetry(value: unknown): AcousticTelemetry {
  const source = record(value, "telemetry.acoustic");
  return {
    source: stringValue(source.source, "telemetry.acoustic.source"),
    rms: numberValue(source.rms, "telemetry.acoustic.rms"),
    peak_amplitude: numberValue(source.peak_amplitude, "telemetry.acoustic.peak_amplitude"),
    crest_factor: numberValue(source.crest_factor, "telemetry.acoustic.crest_factor"),
    energy: numberValue(source.energy, "telemetry.acoustic.energy"),
    dominant_frequency: numberValue(source.dominant_frequency, "telemetry.acoustic.dominant_frequency"),
    spectral_centroid: numberValue(source.spectral_centroid, "telemetry.acoustic.spectral_centroid"),
    spectral_bandwidth: numberValue(source.spectral_bandwidth, "telemetry.acoustic.spectral_bandwidth"),
    spectral_rolloff: numberValue(source.spectral_rolloff, "telemetry.acoustic.spectral_rolloff"),
    spectral_flatness: numberValue(source.spectral_flatness, "telemetry.acoustic.spectral_flatness"),
    spectral_peaks: arrayValue(source.spectral_peaks, "telemetry.acoustic.spectral_peaks").map((item, index) =>
      parseSpectralPeak(item, `telemetry.acoustic.spectral_peaks[${index}]`),
    ),
    band_energies: parseBandAnalysis(source.band_energies, "telemetry.acoustic.band_energies"),
    mfcc: arrayValue(source.mfcc, "telemetry.acoustic.mfcc").map((item, index) =>
      numberValue(item, `telemetry.acoustic.mfcc[${index}]`),
    ),
    ml_prediction: optionalAcousticMlClass(source.ml_prediction, "telemetry.acoustic.ml_prediction"),
    ml_confidence: optionalNumber(source.ml_confidence, "telemetry.acoustic.ml_confidence"),
    ml_reliability: optionalMlReliability(source.ml_reliability, "telemetry.acoustic.ml_reliability"),
    ml_model_version: optionalString(source.ml_model_version, "telemetry.acoustic.ml_model_version"),
  };
}

export function parseThermalTelemetry(value: unknown): ThermalTelemetry {
  const source = record(value, "telemetry.thermal");
  return {
    source: stringValue(source.source, "telemetry.thermal.source"),
    mean_intensity: numberValue(source.mean_intensity, "telemetry.thermal.mean_intensity"),
    max_intensity: numberValue(source.max_intensity, "telemetry.thermal.max_intensity"),
    min_intensity: numberValue(source.min_intensity, "telemetry.thermal.min_intensity"),
    std_intensity: numberValue(source.std_intensity, "telemetry.thermal.std_intensity"),
    hotspot_threshold: numberValue(source.hotspot_threshold, "telemetry.thermal.hotspot_threshold"),
    hotspot_pixel_count: numberValue(source.hotspot_pixel_count, "telemetry.thermal.hotspot_pixel_count"),
    hotspot_area_fraction: numberValue(source.hotspot_area_fraction, "telemetry.thermal.hotspot_area_fraction"),
    hotspot_centroid_x: optionalNumber(source.hotspot_centroid_x, "telemetry.thermal.hotspot_centroid_x"),
    hotspot_centroid_y: optionalNumber(source.hotspot_centroid_y, "telemetry.thermal.hotspot_centroid_y"),
    gradient_mean: numberValue(source.gradient_mean, "telemetry.thermal.gradient_mean"),
    gradient_max: numberValue(source.gradient_max, "telemetry.thermal.gradient_max"),
    is_radiometric: booleanValue(source.is_radiometric, "telemetry.thermal.is_radiometric"),
    ml_prediction: optionalString(source.ml_prediction, "telemetry.thermal.ml_prediction"),
    ml_confidence: optionalNumber(source.ml_confidence, "telemetry.thermal.ml_confidence"),
    ml_condition: optionalString(source.ml_condition, "telemetry.thermal.ml_condition"),
    ml_load_context: optionalString(source.ml_load_context, "telemetry.thermal.ml_load_context"),
    ml_reliability: optionalMlReliability(source.ml_reliability, "telemetry.thermal.ml_reliability"),
    model_version: optionalString(source.model_version, "telemetry.thermal.model_version"),
  };
}

function parseFusionModalityEvidence(value: unknown, path: string): FusionModalityEvidence {
  const source = record(value, path);
  const result: FusionModalityEvidence = {
    available: booleanValue(source.available, `${path}.available`),
    prediction: optionalString(source.prediction, `${path}.prediction`),
    confidence: optionalNumber(source.confidence, `${path}.confidence`),
    reliability: mlReliabilityValue(source.reliability, `${path}.reliability`),
    anomaly_strength: optionalNumber(source.anomaly_strength, `${path}.anomaly_strength`),
    model_version: optionalString(source.model_version, `${path}.model_version`),
    known_limitation: stringValue(source.known_limitation, `${path}.known_limitation`),
  };
  // Thermal-only extension fields - simply absent (not null) on vibration/acoustic.
  if ("condition_context" in source) result.condition_context = optionalString(source.condition_context, `${path}.condition_context`);
  if ("load_context" in source) result.load_context = optionalString(source.load_context, `${path}.load_context`);
  return result;
}

function parseMLFusionTelemetry(value: unknown, path: string): MLFusionTelemetry {
  const source = record(value, path);
  const modalityEvidenceSource = record(source.modality_evidence, `${path}.modality_evidence`);
  return {
    fused_severity: optionalNumber(source.fused_severity, `${path}.fused_severity`),
    fused_confidence: numberValue(source.fused_confidence, `${path}.fused_confidence`),
    reliability: mlFusionReliabilityValue(source.reliability, `${path}.reliability`),
    available_modalities: modalityList(source.available_modalities, `${path}.available_modalities`),
    model_type: stringValue(source.model_type, `${path}.model_type`),
    version: stringValue(source.version, `${path}.version`),
    modality_evidence: {
      thermal: parseFusionModalityEvidence(modalityEvidenceSource.thermal, `${path}.modality_evidence.thermal`),
      vibration: parseFusionModalityEvidence(modalityEvidenceSource.vibration, `${path}.modality_evidence.vibration`),
      acoustic: parseFusionModalityEvidence(modalityEvidenceSource.acoustic, `${path}.modality_evidence.acoustic`),
    },
  };
}

function parseTelemetryEvent(value: unknown, path: string): TelemetryEvent {
  const source = record(value, path);
  return {
    ...source,
    type: stringValue(source.type, `${path}.type`),
    ...(source.status == null ? {} : { status: stringValue(source.status, `${path}.status`) }),
  };
}

export function parseTelemetryPayload(value: unknown): TelemetryPayload {
  const source = record(value, "telemetry");
  const mode = source.mode;
  if (mode !== "demo" && mode !== "live") return fail("telemetry.mode", "demo or live", mode);
  return {
    timestamp: stringValue(source.timestamp, "telemetry.timestamp"),
    machine_id: stringValue(source.machine_id, "telemetry.machine_id"),
    mode,
    thermal: source.thermal == null ? null : parseThermalTelemetry(source.thermal),
    vibration: source.vibration == null ? null : parseVibrationTelemetry(source.vibration),
    acoustic: source.acoustic == null ? null : parseAcousticTelemetry(source.acoustic),
    health: source.health == null ? null : parseMachineHealthState(source.health),
    ml_fusion: source.ml_fusion == null ? null : parseMLFusionTelemetry(source.ml_fusion, "telemetry.ml_fusion"),
    events: arrayValue(source.events ?? [], "telemetry.events").map((item, index) =>
      parseTelemetryEvent(item, `telemetry.events[${index}]`),
    ),
  };
}

export function parseHealthHistory(value: unknown): HealthHistoryPoint[] {
  return arrayValue(value, "history").map((item, index) => {
    const source = record(item, `history[${index}]`);
    return {
      timestamp: stringValue(source.timestamp, `history[${index}].timestamp`),
      health_score: optionalNumber(source.health_score, `history[${index}].health_score`),
      status: healthStatusValue(source.status ?? "unknown", `history[${index}].status`),
      confidence: optionalNumber(source.confidence, `history[${index}].confidence`),
    };
  });
}

export function parseAnomalyEvents(value: unknown): AnomalyEventRecord[] {
  return arrayValue(value, "events").map((item, index) => {
    const source = record(item, `events[${index}]`);
    return {
      event_id: stringValue(source.event_id, `events[${index}].event_id`),
      started_at: stringValue(source.started_at, `events[${index}].started_at`),
      resolved_at: optionalString(source.resolved_at, `events[${index}].resolved_at`),
      severity: stringValue(source.severity, `events[${index}].severity`),
      modality_contributions: numberRecord(source.modality_contributions, `events[${index}].modality_contributions`),
      evidence: jsonObject(source.evidence, `events[${index}].evidence`),
    };
  });
}

function nullableInteger(value: unknown, path: string): number | null {
  const parsed = optionalNumber(value, path);
  return parsed == null || Number.isInteger(parsed) ? parsed : fail(path, "an integer or null", value);
}

export function parseDatasets(value: unknown): DatasetInfo[] {
  return arrayValue(value, "datasets").map((item, index) => {
    const source = record(item, `datasets[${index}]`);
    return {
      dataset_id: stringValue(source.dataset_id, `datasets[${index}].dataset_id`),
      dataset_name: stringValue(source.dataset_name, `datasets[${index}].dataset_name`),
      machine_type: optionalString(source.machine_type, `datasets[${index}].machine_type`),
      modality: stringValue(source.modality, `datasets[${index}].modality`),
      path: stringValue(source.path, `datasets[${index}].path`),
      format: optionalString(source.format, `datasets[${index}].format`),
      sample_count: nullableInteger(source.sample_count, `datasets[${index}].sample_count`),
      sample_rate: optionalNumber(source.sample_rate, `datasets[${index}].sample_rate`),
      channels: nullableInteger(source.channels, `datasets[${index}].channels`),
      normal_count: nullableInteger(source.normal_count, `datasets[${index}].normal_count`),
      anomaly_count: nullableInteger(source.anomaly_count, `datasets[${index}].anomaly_count`),
      notes: optionalString(source.notes, `datasets[${index}].notes`),
    };
  });
}

export function parseDevices(value: unknown): DeviceStatus[] {
  return arrayValue(value, "devices").map((item, index) => {
    const source = record(item, `devices[${index}]`);
    return {
      device_id: stringValue(source.device_id, `devices[${index}].device_id`),
      device_type: stringValue(source.device_type, `devices[${index}].device_type`),
      machine_id: optionalString(source.machine_id, `devices[${index}].machine_id`),
      connection_type: optionalString(source.connection_type, `devices[${index}].connection_type`),
      status: deviceStatusValue(source.status, `devices[${index}].status`),
      configuration: nullableJsonObject(source.configuration, `devices[${index}].configuration`),
      last_seen: optionalString(source.last_seen, `devices[${index}].last_seen`),
    };
  });
}

function stringRecord(value: unknown, path: string): Record<string, string | null> {
  const source = record(value ?? {}, path);
  return Object.fromEntries(
    Object.entries(source).map(([key, item]) => [key, item == null ? null : stringValue(item, `${path}.${key}`)]),
  );
}

export function parseDemoStatus(value: unknown): DemoStatus {
  const source = record(value, "demo");
  if (source.mode != null && source.mode !== "demo") return fail("demo.mode", "demo", source.mode);
  return {
    running: booleanValue(source.running, "demo.running"),
    machine_id: optionalString(source.machine_id, "demo.machine_id"),
    session_id: optionalString(source.session_id, "demo.session_id"),
    mode: "demo",
    sources: stringRecord(source.sources, "demo.sources"),
    started_at: optionalString(source.started_at, "demo.started_at"),
  };
}

export function parseDemoScenarios(value: unknown): DemoScenario[] {
  return arrayValue(value, "demo_scenarios").map((item, index) => {
    const path = `demo_scenarios[${index}]`;
    const source = record(item, path);
    const modality = source.modality;
    if (modality !== "thermal" && modality !== "vibration" && modality !== "acoustic") {
      return fail(`${path}.modality`, "thermal, vibration, or acoustic", modality);
    }
    return {
      scenario_id: stringValue(source.scenario_id, `${path}.scenario_id`),
      label: stringValue(source.label, `${path}.label`),
      modality,
      source: stringValue(source.source, `${path}.source`),
      channel: nullableInteger(source.channel, `${path}.channel`),
      start_file: nullableInteger(source.start_file, `${path}.start_file`),
      end_file: nullableInteger(source.end_file, `${path}.end_file`),
      notes: stringValue(source.notes, `${path}.notes`),
    };
  });
}

export function parseMachineVideos(value: unknown): MachineVideoEntry[] {
  return arrayValue(value, "machine_videos").map((item, index) => {
    const path = `machine_videos[${index}]`;
    const source = record(item, path);
    return {
      machine_video_id: stringValue(source.machine_video_id, `${path}.machine_video_id`),
      name: stringValue(source.name, `${path}.name`),
      video: stringValue(source.video, `${path}.video`),
      video_id: numberValue(source.video_id, `${path}.video_id`),
      machine_type: stringValue(source.machine_type, `${path}.machine_type`),
      path: stringValue(source.path, `${path}.path`),
      notes: stringValue(source.notes, `${path}.notes`),
    };
  });
}

export function parseThermalFeed(value: unknown): ThermalFeedEntry[] {
  return arrayValue(value, "thermal_image_feed").map((item, index) => {
    const path = `thermal_image_feed[${index}]`;
    const source = record(item, path);
    return {
      image_id: stringValue(source.image_id, `${path}.image_id`),
      ml_prediction: optionalString(source.ml_prediction, `${path}.ml_prediction`),
      ml_confidence: optionalNumber(source.ml_confidence, `${path}.ml_confidence`),
      ml_condition: optionalString(source.ml_condition, `${path}.ml_condition`),
      ml_load_context: optionalString(source.ml_load_context, `${path}.ml_load_context`),
      ml_reliability: mlReliabilityValue(source.ml_reliability, `${path}.ml_reliability`),
      model_version: optionalString(source.model_version, `${path}.model_version`),
    };
  });
}

export function safeParse<T>(parser: (value: unknown) => T, value: unknown): SafeParseResult<T> {
  try {
    return { value: parser(value), error: null };
  } catch (error) {
    if (error instanceof ContractError) return { value: null, error };
    throw error;
  }
}

/** Parse a JSON WebSocket message and validate every field used by the UI. */
export function parseTelemetryMessage(value: string): TelemetryPayload {
  let decoded: unknown;
  try {
    decoded = JSON.parse(value) as unknown;
  } catch (error) {
    return fail("telemetry", "valid JSON", error);
  }
  return parseTelemetryPayload(decoded);
}
