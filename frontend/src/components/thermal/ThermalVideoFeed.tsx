import { useState } from "react";
import { thermalVideoUrl } from "../../services/api";
import type { MachineVideoEntry, ThermalTelemetry } from "../../types";
import { DataState } from "../common/DataState";
import { MetricValue } from "../common/MetricValue";
import { Panel } from "../common/Panel";
import { StatusBadge } from "../common/StatusBadge";

interface Props {
  /** Additional class for grid placement in whichever page embeds this
   * (e.g. "sensor-visual-panel" on Fusion, "thermal-feed-panel--full" on
   * the dedicated Thermal page). */
  className?: string;
  /** The machine-video registry entry matching the ACTIVE demo session's
   * thermal source, or null when no session is running / no thermal
   * source is configured. Machine identity always comes from this
   * registry match, never from a video-classifier prediction or the
   * underlying filename - neither is ever shown to the user. */
  activeVideo: MachineVideoEntry | null;
  /** Whether a demo session is currently running at all - used to tell
   * "no session" apart from "session running, no thermal source". */
  sessionRunning: boolean;
  /** Latest thermal feature snapshot for this machine, straight from the
   * existing ThermalAnalyzer/telemetry contract - the reading cards below
   * the video render exactly these fields, nothing invented. */
  thermal: ThermalTelemetry | null;
}

function fmt(digits = 1) {
  return (value: number) => value.toFixed(digits);
}

/**
 * Plays the CURRENTLY ACTIVE demo session's thermal source video, decoded
 * frame-by-frame by the backend's existing ThermalVideoReader / thermal
 * pipeline (see app.services.demo_runner). This <video> element is a
 * visual convenience only, streamed from the same GET /api/demo/thermal-
 * video endpoint the backend already served for the pre-existing thermal
 * video demo - it does not run its own decoding or inference, and it is
 * never the source the deterministic/ML pipeline reads from (the backend
 * reads the file independently).
 *
 * Machine identity comes only from the machine/video registry match
 * (`activeVideo`), never from the video filename or the ML prediction -
 * neither the filename nor a "prerecorded feed" label is shown to the
 * user, matching the product's target UX.
 */
export function ThermalVideoFeed({ className = "", activeVideo, sessionRunning, thermal }: Props) {
  const [videoError, setVideoError] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const key = activeVideo?.path ?? "none";
  const radiometric = thermal?.is_radiometric === true;
  const delta = thermal && Number.isFinite(thermal.max_intensity) && Number.isFinite(thermal.min_intensity)
    ? thermal.max_intensity - thermal.min_intensity
    : null;
  const unit = radiometric ? "°C" : undefined;

  return (
    <Panel tone="ink" className={`thermal-feed-panel ${className}`}>
      <div className="panel-title-row">
        <div>
          <div className="panel-kicker">Thermal feed</div>
          <h2>{activeVideo ? activeVideo.name : "No machine selected"}</h2>
        </div>
        <StatusBadge
          status={videoError ? "error" : !activeVideo ? "unknown" : "normal"}
          label={videoError ? "Feed unavailable" : !activeVideo ? "No video" : "Playing"}
        />
      </div>

      <div className="thermal-feed-panel__stage">
        {!sessionRunning ? (
          <DataState tone="empty" title="No active demo session" description="Select a machine and start the demo session to play its thermal feed." compact />
        ) : !activeVideo ? (
          <DataState tone="empty" title="No thermal video configured" description="Choose a machine from the registry to attach a thermal source." compact />
        ) : videoError ? (
          <DataState tone="error" title="Thermal video unavailable" description="The video source could not be loaded or played back." compact />
        ) : (
          <video
            key={key}
            className="thermal-feed-panel__media"
            src={thermalVideoUrl()}
            autoPlay
            loop
            muted
            playsInline
            controls
            onCanPlay={() => setLoaded(true)}
            onError={() => setVideoError(true)}
            aria-label={`Thermal feed - ${activeVideo.name}`}
          />
        )}
        {sessionRunning && activeVideo && !loaded && !videoError ? (
          <div className="thermal-feed-panel__overlay">
            <DataState tone="loading" title="Loading video" compact />
          </div>
        ) : null}
      </div>

      <div className="thermal-readings">
        <div className="thermal-readings__header">
          <span className="panel-kicker">{radiometric ? "Temperature readings (°C)" : "Thermal intensity readings"}</span>
          {!radiometric ? <span className="thermal-readings__note">Non-radiometric source - relative units, not °C</span> : null}
        </div>
        <div className="thermal-readings__grid">
          <div className="thermal-reading-card">
            <MetricValue label="Mean" value={thermal?.mean_intensity} unit={unit} format={fmt()} hint="Frame average" />
          </div>
          <div className="thermal-reading-card">
            <MetricValue label="Max" value={thermal?.max_intensity} unit={unit} format={fmt()} hint="Peak reading" />
          </div>
          <div className="thermal-reading-card">
            <MetricValue label="Min" value={thermal?.min_intensity} unit={unit} format={fmt()} hint="Coolest reading" />
          </div>
          <div className="thermal-reading-card">
            <MetricValue label="Hotspot threshold" value={thermal?.hotspot_threshold} unit={unit} format={fmt()} hint="Hotspot cutoff" />
          </div>
          <div className="thermal-reading-card">
            <MetricValue label="Hotspot area" value={thermal ? thermal.hotspot_area_fraction * 100 : null} unit="%" format={fmt()} hint="Share of frame above threshold" />
          </div>
          <div className="thermal-reading-card">
            <MetricValue label="ΔT" value={delta} unit={unit} format={fmt()} hint="Max − min" />
          </div>
        </div>
      </div>

      <p className="chart-note thermal-feed-panel__footnote">
        Simulated sensor input - a prerecorded video demo, not a live physical thermal camera.
      </p>
    </Panel>
  );
}
