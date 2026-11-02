/**
 * Types shared by the REST and telemetry boundaries.
 *
 * These are deliberately DTO-shaped types. Health/anomaly calculations are
 * performed by the backend; the frontend only formats and visualises these
 * values.
 */

export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonObject | JsonValue[];
export interface JsonObject {
  [key: string]: JsonValue;
}

export type Modality = "thermal" | "vibration" | "acoustic";
export type HealthStatus = "normal" | "warning" | "critical" | "unknown";
export type TelemetryMode = "demo" | "live";

/**
 * Per-modality ML confidence-gate reliability (Thermal ML V1 / Vibration ML
 * V1 / Acoustic ML V1). "high" means the modality's OWN engineering
 * threshold was cleared for this reading - it does not mean cross-condition
 * generalization has been proven for that model. See each modality's
 * `known_limitation` string surfaced through ML Fusion evidence.
 */
export type MLReliability = "high" | "low" | "unavailable";

/** Reliability of the multimodal ML evidence fusion result specifically -
 * a distinct three-way scale from MLReliability because it also expresses
 * partial modality coverage. */
export type MLFusionReliability = "high" | "partial" | "unavailable";

/**
 * One entry in the curated Thermal V1 dataset image feed
 * (GET /api/demo/thermal-image-feed) - a real, held-out test-split image
 * with the existing Thermal ML V1 model + confidence gate already applied
 * once (cached server-side). Not tied to a running demo session.
 */
export interface ThermalFeedEntry {
  image_id: string;
  /** Known label of this held-out test image, from the saved split manifest (not a model output). */
  true_class: string | null;
  ml_prediction: string | null;
  /** The model's raw best guess, also when it is below the reliability threshold (then `ml_prediction` is null). */
  ml_top_class: string | null;
  ml_confidence: number | null;
  ml_condition: string | null;
  ml_load_context: string | null;
  ml_reliability: MLReliability;
  model_version: string | null;
}

/** Saved held-out TEST-image results of the thermal classifier (not measured on the demo videos). */
export interface ThermalEvaluation {
  model_version: string | null;
  accuracy: number;
  macro_f1: number;
  top3_accuracy: number;
  test_count: number | null;
}

export interface HealthResponse {
  status: string;
  app: string;
  environment: string;
}

export interface MachineCreate {
  machine_name: string;
  machine_type?: string | null;
  manufacturer?: string | null;
  model?: string | null;
  rpm?: number | null;
  rated_power?: number | null;
  location?: string | null;
  sensor_configuration?: JsonObject | null;
}

export interface Machine extends MachineCreate {
  machine_id: string;
  machine_type: string | null;
  manufacturer: string | null;
  model: string | null;
  rpm: number | null;
  rated_power: number | null;
  location: string | null;
  sensor_configuration: JsonObject | null;
  baseline_status: string;
  monitoring_status: string;
  created_at: string;
}

export interface EvidenceItem {
  modality: Modality;
  feature: string;
  value: number | null;
  baseline_mean: number | null;
  deviation: number | null;
  note: string | null;
}

export interface MachineHealthState {
  machine_id: string;
  timestamp: string;
  health_score: number | null;
  status: HealthStatus;
  severity: string | null;
  confidence: number | null;
  modality_contributions: Record<string, number>;
  missing_modalities: Modality[];
  evidence: EvidenceItem[];
  model_version: string | null;
}

export interface BandEnergy {
  center_frequency: number;
  low_frequency: number;
  high_frequency: number;
  energy: number;
}

export interface BandAnalysisResult {
  band_type: "octave" | "third_octave";
  bands: BandEnergy[];
}

export interface SpectralPeak {
  frequency: number;
  magnitude: number;
}

export interface BearingFaultFrequencies {
  bpfo: number;
  bpfi: number;
  bsf: number;
  ftf: number;
}

export interface VibrationTelemetry {
  source: string;
  rms: number;
  variance: number;
  std: number;
  peak: number;
  peak_to_peak: number;
  crest_factor: number;
  kurtosis: number;
  skewness: number;
  dominant_frequency: number;
  spectral_centroid: number;
  spectral_bandwidth: number;
  spectral_peaks: SpectralPeak[];
  /** Vibration extraction may legitimately omit band analysis. */
  band_energies: BandAnalysisResult | null;
  analysis_type: "generic_spectral" | "bearing_specific";
  bearing_fault_frequencies: BearingFaultFrequencies | null;
  /**
   * Vibration ML V1 (Random Forest) evidence, merged in only when the
   * runtime ML model produced a reading for this window. IMPORTANT: these
   * classes are a project-DERIVED labeling rule applied to the IMS
   * degradation trajectory, not original dataset ground truth - this is a
   * derived-label trajectory classifier, not an independently validated
   * fault detector. `null` means the confidence gate suppressed the
   * prediction (low confidence) or the model was unavailable - never a
   * definitive health state in that case, though `ml_confidence` is still
   * reported when known.
   */
  ml_prediction: "healthy" | "degrading" | "severe" | null;
  ml_confidence: number | null;
  ml_reliability: MLReliability | null;
  ml_model_version: string | null;
}

export interface AcousticTelemetry {
  source: string;
  rms: number;
  peak_amplitude: number;
  crest_factor: number;
  energy: number;
  dominant_frequency: number;
  spectral_centroid: number;
  spectral_bandwidth: number;
  spectral_rolloff: number;
  spectral_flatness: number;
  spectral_peaks: SpectralPeak[];
  band_energies: BandAnalysisResult;
  mfcc: number[];
  /**
   * Acoustic ML V1 (Logistic Regression) evidence, merged in only when the
   * runtime ML model produced a reading for this clip. IMPORTANT: measured
   * test performance varies across recording section/domain groups
   * (macro-F1 0.789-0.965) - a "high" reliability reading reflects LOCAL
   * confidence only, not proven cross-section generalization. `null` means
   * the confidence gate suppressed the prediction or the model was
   * unavailable - `ml_confidence` is still reported when known.
   */
  ml_prediction: "normal" | "anomaly" | null;
  ml_confidence: number | null;
  ml_reliability: MLReliability | null;
  ml_model_version: string | null;
}

export interface ThermalTelemetry {
  source: string;
  mean_intensity: number;
  max_intensity: number;
  min_intensity: number;
  std_intensity: number;
  hotspot_threshold: number;
  hotspot_pixel_count: number;
  hotspot_area_fraction: number;
  hotspot_centroid_x: number | null;
  hotspot_centroid_y: number | null;
  gradient_mean: number;
  gradient_max: number;
  /** Current demo sources are non-radiometric intensity frames. */
  is_radiometric: boolean;
  /**
   * Thermal ML V1 (MobileNetV3-Small) evidence, merged in only when the
   * runtime ML model produced a reading for this frame. IMPORTANT: this
   * model's known limitation is significant load-level confusion
   * (CFL<->CML, HML->HFL) - confidence does not reliably separate that
   * error mode. `ml_prediction` is `null` when the confidence gate
   * suppressed the reading or the model was unavailable; `ml_confidence`
   * is still reported when known.
   */
  ml_prediction: string | null;
  /** The model's raw best guess, also when it is below the reliability threshold (then `ml_prediction` is null). */
  ml_top_class: string | null;
  ml_confidence: number | null;
  ml_condition: string | null;
  ml_load_context: string | null;
  ml_reliability: MLReliability | null;
  /** Note: thermal's own gate names this field `model_version`, not
   * `ml_model_version` (an existing backend naming asymmetry vs. vibration/
   * acoustic - preserved here rather than silently "fixed"). */
  model_version: string | null;
}

export interface TelemetryEvent {
  type: string;
  status?: HealthStatus | string;
  [key: string]: unknown;
}

/**
 * Multimodal ML Evidence Fusion V1 - a SUPPLEMENTARY, weighted-evidence
 * combination of the three modalities' own ML confidence-gate outputs.
 * This is NOT the deterministic machine health (MachineHealthState) and
 * must never be presented as a probability of failure - see
 * `fused_severity`'s own limitation: it is a confidence-weighted average
 * of heterogeneous per-modality anomaly_strength mappings, not a
 * calibrated health score. A suppressed or missing modality contributes
 * zero weight - `available_modalities` lists only modalities that
 * actually contributed to the fused numbers below.
 */
export interface FusionModalityEvidence {
  available: boolean;
  prediction: string | null;
  confidence: number | null;
  reliability: MLReliability;
  anomaly_strength: number | null;
  model_version: string | null;
  /** Fixed, non-editable-at-runtime limitation string carried forward from
   * that modality's own V1 task - never hidden by fusion. */
  known_limitation: string;
  condition_context?: string | null;
  load_context?: string | null;
}

export interface MLFusionTelemetry {
  fused_severity: number | null;
  fused_confidence: number;
  reliability: MLFusionReliability;
  available_modalities: Modality[];
  model_type: string;
  version: string;
  modality_evidence: {
    thermal: FusionModalityEvidence;
    vibration: FusionModalityEvidence;
    acoustic: FusionModalityEvidence;
  };
}

/** Real replay position reported by the backend's file reader. Absent when the backend cannot report it. */
export interface PlaybackProgress {
  unit: "seconds" | "files";
  position: number;
  total: number;
  /** How many times the recording has been (re)started; the demo loops when a recording ends. */
  loop: number;
}

export interface TelemetryPayload {
  timestamp: string;
  machine_id: string;
  mode: TelemetryMode;
  thermal: ThermalTelemetry | null;
  vibration: VibrationTelemetry | null;
  acoustic: AcousticTelemetry | null;
  health: MachineHealthState | null;
  ml_fusion: MLFusionTelemetry | null;
  events: TelemetryEvent[];
  progress: Partial<Record<Modality, PlaybackProgress>>;
}

/** Bounded chart projection of backend envelopes retained by the browser. */
export interface TelemetrySeriesPoint {
  timestamp: string;
  mode: TelemetryMode;
  thermal: Pick<ThermalTelemetry, "mean_intensity" | "max_intensity" | "hotspot_area_fraction" | "gradient_mean"> | null;
  vibration: Pick<VibrationTelemetry, "rms" | "dominant_frequency" | "crest_factor"> | null;
  acoustic: Pick<AcousticTelemetry, "rms" | "dominant_frequency" | "spectral_centroid"> | null;
}

export interface HealthHistoryPoint {
  timestamp: string;
  health_score: number | null;
  status: HealthStatus;
  confidence: number | null;
}

export interface AnomalyEventRecord {
  event_id: string;
  started_at: string;
  resolved_at: string | null;
  severity: string;
  modality_contributions: Record<string, number>;
  evidence: JsonObject;
}

export interface DatasetInfo {
  dataset_id: string;
  dataset_name: string;
  machine_type: string | null;
  /** The backend keeps this extensible rather than restricting it to the three live modalities. */
  modality: string;
  path: string;
  format: string | null;
  sample_count: number | null;
  sample_rate: number | null;
  channels: number | null;
  normal_count: number | null;
  anomaly_count: number | null;
  notes: string | null;
}

export type DeviceConnectionStatus = "connected" | "not_connected" | "error";

export interface DeviceStatus {
  device_id: string;
  device_type: string;
  machine_id: string | null;
  connection_type: string | null;
  status: DeviceConnectionStatus;
  configuration: JsonObject | null;
  last_seen: string | null;
}

export interface DemoStartRequest {
  machine_id: string;
  thermal_source?: string | null;
  vibration_source?: string | null;
  vibration_channel?: number;
  vibration_start_file?: number;
  vibration_end_file?: number;
  acoustic_source?: string | null;
  playback_speed?: number;
}

/**
 * One entry in the authoritative machine -> prerecorded thermal video
 * registry (GET /api/demo/machine-videos) - the single source of truth the
 * machine selector reads from. `path` is the absolute source path used
 * exactly as-is for `DemoStartRequest.thermal_source`; the user never types
 * a machine name or a video path. Video 6 is a generic/unidentified clip
 * and is never present here.
 */
export interface MachineVideoEntry {
  machine_video_id: string;
  name: string;
  video: string;
  video_id: number;
  machine_type: string;
  path: string;
  notes: string;
}

export interface DemoScenario {
  scenario_id: string;
  label: string;
  modality: Modality;
  source: string;
  channel: number | null;
  start_file: number | null;
  end_file: number | null;
  notes: string;
}

export interface DemoStatus {
  running: boolean;
  machine_id: string | null;
  session_id: string | null;
  mode: "demo";
  sources: Record<string, string | null>;
  started_at: string | null;
}
