import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useId, type ReactNode } from "react";
import type { BandAnalysisResult, BandEnergy, HealthHistoryPoint, SpectralPeak } from "../../types";
import { DataState } from "../common/DataState";

const CHART_COLORS = {
  grid: "rgba(15, 41, 71, 0.12)",
  axis: "#64748B",
  health: "#15803D",
  vibration: "#1D74C9",
  acoustic: "#B45309",
  thermal: "#0D9488",
  neutral: "#3F5872",
  unknown: "#64748B",
} as const;

const chartTextStyle = { fontSize: 10, fill: CHART_COLORS.axis };
const tooltipContentStyle = {
  background: "#FFFFFF",
  border: "1px solid #D9E2EC",
  borderRadius: 5,
  color: "#0F2947",
  fontSize: 12,
  boxShadow: "0 4px 16px rgba(15, 41, 71, 0.12)",
};
const tooltipLabelStyle = { color: CHART_COLORS.neutral };
const chartActiveDotStroke = "#FFFFFF";

export interface ChartFrameProps {
  title: string;
  eyebrow?: string;
  description?: string;
  source?: string;
  accessibleSummary?: string;
  children: ReactNode;
  empty?: boolean;
  emptyTitle?: string;
  emptyDescription?: string;
  className?: string;
  contentClassName?: string;
}

/** Shared chart frame with explicit provenance and an assistive text summary. */
export function ChartFrame({
  title,
  eyebrow,
  description,
  source,
  accessibleSummary,
  children,
  empty = false,
  emptyTitle = "No measurements available",
  emptyDescription = "This view will populate when the backend provides a valid measurement.",
  className = "",
  contentClassName = "",
}: ChartFrameProps) {
  const reactId = useId();
  const titleId = `chart-${title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-${reactId.replace(/[^a-z0-9_-]/gi, "")}`;

  return (
    <section aria-labelledby={titleId} className={`chart-frame ${className}`}>
      <header className="chart-frame__header">
        <div className="min-w-0">
          {eyebrow ? <p className="chart-frame__eyebrow">{eyebrow}</p> : null}
          <h3 id={titleId} className="chart-frame__title">{title}</h3>
          {description ? <p className="chart-frame__description">{description}</p> : null}
        </div>
        {source ? <p className="chart-frame__source">{source}</p> : null}
      </header>
      {empty ? (
        <DataState
          tone="empty"
          title={emptyTitle}
          description={emptyDescription}
          compact
          surface="dark"
          className="chart-frame__empty"
        />
      ) : (
        <div className={`chart-frame__content ${contentClassName}`}>
          <div role="img" aria-label={accessibleSummary ?? title}>
            {children}
          </div>
          {accessibleSummary ? <p className="sr-only">{accessibleSummary}</p> : null}
        </div>
      )}
    </section>
  );
}

function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatNumber(value: number | null | undefined, digits = 2): string {
  return value === null || value === undefined || !Number.isFinite(value) ? "—" : value.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function formatTime(timestamp: string): string {
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatFrequency(value: number): string {
  return value >= 1000 ? `${(value / 1000).toFixed(value >= 10000 ? 0 : 1)}k` : Math.round(value).toString();
}

function chartInterval(length: number): number | "preserveStartEnd" {
  return length > 15 ? Math.ceil(length / 10) - 1 : 0;
}

export interface SignalTrendPoint {
  timestamp: string;
  [key: string]: string | number | null;
}

export interface SignalTrendSeries {
  key: string;
  label: string;
  color: string;
}

export interface SignalTrendChartProps {
  title: string;
  data: readonly SignalTrendPoint[];
  series: readonly SignalTrendSeries[];
  source?: string;
  unit?: string;
  height?: number;
  className?: string;
  emptyTitle?: string;
  emptyDescription?: string;
}

/** Draws only backend-derived samples; unavailable and missing values remain gaps. */
export function SignalTrendChart({
  title,
  data,
  series,
  source = "WebSocket telemetry",
  unit = "",
  height = 190,
  className = "",
  emptyTitle = "Waiting for telemetry",
  emptyDescription = "No valid measurement for this view has arrived yet.",
}: SignalTrendChartProps) {
  const hasData = data.some((point) => series.some((item) => finiteNumber(point[item.key]) !== null));
  const numericValues = data.flatMap((point) => series.map((item) => finiteNumber(point[item.key]))).filter((value): value is number => value !== null);
  const accessibleSummary = hasData
    ? `${title}: ${numericValues.length} valid measurement values across ${data.length} received samples. ${series.map((item) => item.label).join(", ")}.`
    : undefined;
  const chartData = data.map((point) => ({ ...point, time: formatTime(point.timestamp) }));

  return (
    <ChartFrame
      title={title}
      source={source}
      accessibleSummary={accessibleSummary}
      empty={!hasData}
      emptyTitle={emptyTitle}
      emptyDescription={emptyDescription}
      className={className}
    >
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={chartData} margin={{ top: 8, right: 10, left: 0, bottom: 3 }}>
          <CartesianGrid vertical={false} stroke={CHART_COLORS.grid} strokeDasharray="2 4" />
          <XAxis dataKey="time" tick={chartTextStyle} axisLine={false} tickLine={false} interval="preserveStartEnd" minTickGap={28} />
          <YAxis tick={chartTextStyle} axisLine={false} tickLine={false} width={42} />
          <Tooltip
            contentStyle={tooltipContentStyle}
            labelStyle={tooltipLabelStyle}
            formatter={(value, name) => [`${formatNumber(typeof value === "number" ? value : Number(value), 2)}${unit ? ` ${unit}` : ""}`, String(name)]}
          />
          {series.map((item) => (
            <Line
              key={item.key}
              type="monotone"
              dataKey={item.key}
              name={item.label}
              stroke={item.color}
              strokeWidth={1.8}
              dot={false}
              activeDot={{ r: 3, fill: item.color, stroke: chartActiveDotStroke, strokeWidth: 1.5 }}
              connectNulls={false}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

interface ChartDatum {
  label: string;
  value: number | null;
}

export interface HealthTrendChartProps {
  points: readonly HealthHistoryPoint[] | null | undefined;
  title?: string;
  description?: string;
  source?: string;
  height?: number;
  className?: string;
}

export function HealthTrendChart({
  points,
  title = "Health history",
  description = "Backend health score over recorded fusion samples.",
  source = "REST history + live samples",
  height = 208,
  className = "",
}: HealthTrendChartProps) {
  const data = (points ?? []).map((point) => ({
    time: formatTime(point.timestamp),
    timestamp: point.timestamp,
    score: finiteNumber(point.health_score),
    status: point.status,
  }));
  const numericScores = data.map((point) => point.score).filter((score): score is number => score !== null);
  const latest = numericScores.at(-1);
  const accessibleSummary = numericScores.length
    ? `${title}: ${numericScores.length} valid health score samples. Latest ${formatNumber(latest, 1)} out of 100; range ${formatNumber(Math.min(...numericScores), 1)} to ${formatNumber(Math.max(...numericScores), 1)}.`
    : undefined;

  return (
    <ChartFrame
      title={title}
      description={description}
      source={source}
      accessibleSummary={accessibleSummary}
      empty={numericScores.length === 0}
      emptyTitle="No health history"
      emptyDescription="The backend has not returned a valid health score for this machine yet. Unknown is not displayed as zero."
      className={className}
    >
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 10, right: 8, left: 0, bottom: 4 }}>
          <CartesianGrid vertical={false} stroke={CHART_COLORS.grid} strokeDasharray="2 4" />
          <XAxis dataKey="time" tick={chartTextStyle} axisLine={false} tickLine={false} interval="preserveStartEnd" minTickGap={24} />
          <YAxis domain={[0, 100]} tick={chartTextStyle} axisLine={false} tickLine={false} width={32} />
          <Tooltip
            contentStyle={tooltipContentStyle}
            labelStyle={tooltipLabelStyle}
            formatter={(value) => [formatNumber(typeof value === "number" ? value : Number(value), 1), "Health score"]}
          />
          <Line
            type="monotone"
            dataKey="score"
            name="Health score"
            stroke={CHART_COLORS.health}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, fill: CHART_COLORS.health, stroke: chartActiveDotStroke, strokeWidth: 2 }}
            connectNulls={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

export interface ModalityContributionChartProps {
  contributions: Readonly<Record<string, number | null | undefined>> | null | undefined;
  title?: string;
  description?: string;
  source?: string;
  height?: number;
  className?: string;
}

export function ModalityContributionChart({
  contributions,
  title = "Modality contribution",
  description = "Relative severity contribution returned by the backend fusion engine.",
  source = "Fusion output",
  height = 184,
  className = "",
}: ModalityContributionChartProps) {
  const data = Object.entries(contributions ?? {})
    .map(([modality, rawValue]) => ({ modality, value: finiteNumber(rawValue) }))
    .filter((item): item is { modality: string; value: number } => item.value !== null)
    .sort((a, b) => b.value - a.value);
  const accessibleSummary = data.length
    ? `${title}: ${data.map((item) => `${item.modality} ${formatNumber(item.value * 100, 1)} percent`).join(", ")}.`
    : undefined;

  return (
    <ChartFrame
      title={title}
      description={description}
      source={source}
      accessibleSummary={accessibleSummary}
      empty={data.length === 0}
      emptyTitle="No contribution evidence"
      emptyDescription="The fusion engine has not returned a calibrated modality contribution yet."
      className={className}
    >
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} layout="vertical" margin={{ top: 2, right: 12, left: 8, bottom: 2 }}>
          <CartesianGrid horizontal={false} stroke={CHART_COLORS.grid} strokeDasharray="2 4" />
          <XAxis type="number" domain={[0, 1]} tick={chartTextStyle} axisLine={false} tickLine={false} tickFormatter={(value) => `${Math.round(Number(value) * 100)}%`} />
          <YAxis type="category" dataKey="modality" tick={chartTextStyle} axisLine={false} tickLine={false} width={68} tickFormatter={(value) => String(value).replace(/\b\w/g, (char) => char.toUpperCase())} />
          <Tooltip
            contentStyle={tooltipContentStyle}
            labelStyle={tooltipLabelStyle}
            formatter={(value) => [`${formatNumber(Number(value) * 100, 1)}%`, "Contribution"]}
          />
          <Bar dataKey="value" name="Contribution" fill={CHART_COLORS.vibration} barSize={18} radius={[0, 2, 2, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

export interface SpectralPeaksChartProps {
  peaks: readonly SpectralPeak[] | null | undefined;
  title?: string;
  description?: string;
  source?: string;
  height?: number;
  className?: string;
  color?: string;
}

export function SpectralPeaksChart({
  peaks,
  title = "Spectral peaks",
  description = "Dominant frequencies returned by the modality analyzer.",
  source = "Telemetry",
  height = 190,
  className = "",
  color = CHART_COLORS.vibration,
}: SpectralPeaksChartProps) {
  const data = (peaks ?? [])
    .map((peak) => ({ frequency: finiteNumber(peak.frequency), magnitude: finiteNumber(peak.magnitude) }))
    .filter((peak): peak is { frequency: number; magnitude: number } => peak.frequency !== null && peak.magnitude !== null)
    .sort((a, b) => a.frequency - b.frequency)
    .map((peak) => ({ ...peak, label: formatFrequency(peak.frequency) }));
  const strongest = data.reduce<{ frequency: number; magnitude: number } | null>((current, item) => (!current || item.magnitude > current.magnitude ? item : current), null);
  const accessibleSummary = data.length
    ? `${title}: ${data.length} peaks. Strongest at ${formatNumber(strongest?.frequency, 1)} hertz with magnitude ${formatNumber(strongest?.magnitude, 3)}.`
    : undefined;

  return (
    <ChartFrame
      title={title}
      description={description}
      source={source}
      accessibleSummary={accessibleSummary}
      empty={data.length === 0}
      emptyTitle="No spectral peaks"
      emptyDescription="The backend did not provide valid frequency-peak measurements for this modality."
      className={className}
    >
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 4 }}>
          <CartesianGrid vertical={false} stroke={CHART_COLORS.grid} strokeDasharray="2 4" />
          <XAxis dataKey="label" tick={chartTextStyle} axisLine={false} tickLine={false} interval={chartInterval(data.length)} />
          <YAxis tick={chartTextStyle} axisLine={false} tickLine={false} width={42} />
          <Tooltip
            contentStyle={tooltipContentStyle}
            labelStyle={tooltipLabelStyle}
            formatter={(value) => [formatNumber(Number(value), 3), "Magnitude"]}
            labelFormatter={(label) => `${label} Hz`}
          />
          <Bar dataKey="magnitude" name="Magnitude" fill={color} barSize={data.length > 12 ? undefined : 18} radius={[2, 2, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

export interface BandEnergyChartProps {
  data: BandAnalysisResult | null | undefined;
  title?: string;
  description?: string;
  source?: string;
  height?: number;
  className?: string;
  color?: string;
}

export function BandEnergyChart({
  data: bandResult,
  title = "Band energy",
  description,
  source = "Telemetry",
  height = 190,
  className = "",
  color = CHART_COLORS.acoustic,
}: BandEnergyChartProps) {
  const bands: BandEnergy[] = bandResult?.bands ?? [];
  const data = bands
    .map((band) => ({
      center: finiteNumber(band.center_frequency),
      low: finiteNumber(band.low_frequency),
      high: finiteNumber(band.high_frequency),
      energy: finiteNumber(band.energy),
    }))
    .filter((band): band is { center: number; low: number | null; high: number | null; energy: number } => band.center !== null && band.energy !== null)
    .sort((a, b) => a.center - b.center)
    .map((band) => ({ ...band, label: formatFrequency(band.center) }));
  const highest = data.reduce<{ center: number; energy: number } | null>((current, item) => (!current || item.energy > current.energy ? item : current), null);
  const bandLabel = bandResult?.band_type === "third_octave" ? "1/3-octave" : bandResult?.band_type === "octave" ? "octave" : "frequency";
  const accessibleSummary = data.length
    ? `${title}: ${data.length} ${bandLabel} bands. Highest energy is ${formatNumber(highest?.energy, 3)} at ${formatNumber(highest?.center, 1)} hertz.`
    : undefined;

  return (
    <ChartFrame
      title={title}
      description={description ?? `Energy across ${bandLabel} frequency bands.`}
      source={source}
      accessibleSummary={accessibleSummary}
      empty={data.length === 0}
      emptyTitle="No band energy"
      emptyDescription="The backend did not provide valid frequency-band energy measurements for this modality."
      className={className}
    >
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 4 }}>
          <CartesianGrid vertical={false} stroke={CHART_COLORS.grid} strokeDasharray="2 4" />
          <XAxis dataKey="label" tick={chartTextStyle} axisLine={false} tickLine={false} interval={chartInterval(data.length)} />
          <YAxis tick={chartTextStyle} axisLine={false} tickLine={false} width={42} />
          <Tooltip
            contentStyle={tooltipContentStyle}
            labelStyle={tooltipLabelStyle}
            formatter={(value) => [formatNumber(Number(value), 3), "Energy"]}
            labelFormatter={(label) => `${label} Hz`}
          />
          <Bar dataKey="energy" name="Energy" fill={color} barSize={data.length > 12 ? undefined : 18} radius={[2, 2, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

export interface MfccChartProps {
  mfcc: readonly (number | null | undefined)[] | null | undefined;
  title?: string;
  description?: string;
  source?: string;
  height?: number;
  className?: string;
  color?: string;
}

export function MfccChart({
  mfcc,
  title = "MFCC coefficients",
  description = "Averaged mel-frequency cepstral coefficients from acoustic telemetry.",
  source = "Telemetry",
  height = 176,
  className = "",
  color = CHART_COLORS.acoustic,
}: MfccChartProps) {
  const data: ChartDatum[] = (mfcc ?? []).map((value, index) => ({ label: `c${index}`, value: finiteNumber(value) }));
  const valid = data.filter((item): item is { label: string; value: number } => item.value !== null);
  const accessibleSummary = valid.length
    ? `${title}: ${valid.length} valid coefficients. Range ${formatNumber(Math.min(...valid.map((item) => item.value)), 3)} to ${formatNumber(Math.max(...valid.map((item) => item.value)), 3)}.`
    : undefined;

  return (
    <ChartFrame
      title={title}
      description={description}
      source={source}
      accessibleSummary={accessibleSummary}
      empty={valid.length === 0}
      emptyTitle="No MFCC data"
      emptyDescription="The acoustic analyzer has not provided valid MFCC coefficients yet."
      className={className}
    >
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 4 }}>
          <CartesianGrid vertical={false} stroke={CHART_COLORS.grid} strokeDasharray="2 4" />
          <XAxis dataKey="label" tick={chartTextStyle} axisLine={false} tickLine={false} interval={0} />
          <YAxis tick={chartTextStyle} axisLine={false} tickLine={false} width={42} />
          <Tooltip contentStyle={tooltipContentStyle} labelStyle={tooltipLabelStyle} formatter={(value) => [formatNumber(Number(value), 3), "Coefficient"]} />
          <Bar dataKey="value" name="Coefficient" fill={color} barSize={18} radius={[2, 2, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

// Short aliases keep page-level imports readable while preserving the
// descriptive component names for consumers that prefer them.
export const HealthSparkline = HealthTrendChart;
export const TrendChart = HealthTrendChart;
export const BandChart = BandEnergyChart;
export const PeakChart = SpectralPeaksChart;
export const MfcChart = MfccChart;
