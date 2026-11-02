# Visual Direction

## Decision

- **Primary style:** Mission Control / Industrial Monitoring Dashboard
- **Supporting styles:** Data-Dense and Tactical UI

The supplied reference is the primary visual authority for this rebuild. The previous Swiss/editorial and pale instrument-paper direction is retired. This product is a live engineering console: its shell, state hierarchy, controls, and charts should feel like one connected monitoring workstation rather than a collection of standalone SaaS cards.

The reference's proportions and visual language are retained while unsupported example content is not. In particular, the repository does not expose thermal frames, processing FPS, frame counts, or a standalone anomaly score. A dark telemetry chart or an explicit waiting state will occupy the sensor-visualization region; no synthetic image or metric will be introduced.

## Visual philosophy

- Let machine health, data presence, and connection state be legible within a glance.
- Keep the frame dense and operational, with the selected asset and its source context close to the data.
- Use color to encode state and interaction, not as decoration.
- Treat `unknown`, `missing`, and `disconnected` as distinct first-class states.
- Prefer precise grid alignment, small technical labels, and compact readouts over large type or generous whitespace.
- Use the same dark instrument language across Fusion, Thermal, Vibration, Acoustic, Events, Machines, Datasets, Devices, and Demo.
- Use real telemetry and API fields only. The frontend does not calculate health, anomaly, confidence, calibration, or fusion values.

## Spacing system

Use a compact 4px base scale:

- 4px: icon alignment, chart legend gaps, inline state markers.
- 8px: row gaps, compact control spacing, panel-to-panel gutters.
- 12px: metric cells, panel headers, form groups.
- 16px: module padding and page edge padding at desktop.
- 24px: large module separation only where the grid requires it.

Avoid oversized page margins and blank bands. At 1920×1080, the top bar and most of the fusion workspace should remain visible without scrolling when the data is sparse.

## Typography hierarchy

Use a locally available system sans stack (Segoe UI Variable, Segoe UI, system-ui) for interface text and a monospace stack for IDs, timestamps, and tabular measurements. Do not rely on remote font loading.

- Brand: compact uppercase wordmark with a small technical mark and one-line product descriptor.
- Navigation: 12–13px, medium weight; active item distinguished by a blue-toned surface and state border.
- Page/machine heading: 18–24px; no oversized hero treatment.
- Panel heading: 12–14px, semibold, compact uppercase or title case.
- Metric value: 16–24px depending on importance; use tabular numerals.
- Metric label/unit: 10–12px, cool muted gray-blue.
- Chart axis/timestamp: 9–11px with enough contrast to remain legible.

Avoid 50px+ headings and equal emphasis for every number.

## Border and radius systems

- Borders: thin 1px cool blue-gray lines, with slightly brighter borders for focused/selected controls.
- Primary panel radius: 6px.
- Inputs and controls: 4–5px.
- Inner metric regions: square or 3px corners.
- Status dots may be circular; pills are reserved for explicit compact statuses.

Avoid the old high-radius card treatment. A stronger left edge or compact marker may emphasize a warning/critical state; do not flood an entire panel red.

## Elevation and surface hierarchy

Use tone and border contrast as the primary separation mechanism. Shadows are limited to transient menus/overlays; the dashboard itself should not appear to float.

1. **Application ground:** blue-black `#071321` / `#081827`.
2. **Header and inset regions:** deep navy `#0b1b2c`.
3. **Instrument panel:** `#0e2133` to `#10263a`.
4. **Raised control surface:** `#142b41`.
5. **Selected/focus surface:** muted blue `#12345a`, border `#1e80c9`.
6. **Overlay/menu surface:** `#102236`, opaque with a cool border.

No cream or white analytical surfaces. Gradients are optional, subtle, blue-toned, and limited to a panel background where they improve separation.

## Color semantics

Keep colors centralized as semantic tokens:

- **Primary technical accent / focus:** cyan-blue `#259bf0` / `#45b6f2`.
- **Healthy / normal:** green `#38d987`.
- **Warning / dataset demo:** amber `#f4c542`.
- **Critical:** red `#f16b73`.
- **Informational:** blue `#54aef5`.
- **Unknown / unavailable / disconnected:** slate `#8298ad` with explicit text state.
- **Primary text:** cool near-white `#e6eef7`.
- **Secondary text:** cool light gray `#b2c0cf`.
- **Muted labels / axes:** blue-gray `#8298ad`.
- **Borders / chart grid:** subdued blue-gray at low opacity.

Demo amber is a dataset-simulation indicator, not proof of a healthy system. Every state pairs color with a text label or icon.

## Health and data-state semantics

- Backend `normal`, `warning`, `critical`, and `unknown` are displayed as returned. `unknown` never maps to green.
- Show the health gauge only from a numeric backend `health_score`; show an unavailable glyph/state otherwise.
- Show `confidence` as the backend's confidence value, with nearby clarification that it represents evidence coverage, not probability.
- Baseline/calibration wording is based on actual backend baseline/evidence output. A `not_calibrated` machine flag must not be recast as normal.
- Missing telemetry is not zero. A disconnected device is not connected. An open WebSocket without a received envelope is “Connected · awaiting envelope,” not “Telemetry live.”
- Thermal data is relative intensity unless `is_radiometric` is true. The current source/readers mark frames non-radiometric; do not use degrees Celsius, thermal imagery, or temperature palettes as if calibrated.
- Dataset mode is shown only when the actual latest envelope or demo status says `demo` / `running`; never use an amber demo badge to imply live hardware.

## Chart styling

- Reuse Recharts and its existing DTO-driven series.
- Dark transparent plotting surfaces; fine, low-contrast gridlines; restrained axis labels and compact legends.
- Use semantic series colors consistently: cyan/blue for signal, green for health, amber for a separate secondary series, and red only for critical state.
- Preserve original backend units/scales. Do not normalize anomaly scores or derive a score where none is supplied.
- Time-series entries come from REST history or bounded WebSocket samples. Empty charts state what is awaited; they do not draw a synthetic zero line.
- No waveform, spectrogram, thermal frame, anomaly score, or FPS unless that exact data becomes available from the backend.

## Data-density and composition strategy

The desktop Fusion overview follows the reference's operational zones: compact horizontal top navigation; a narrow source/demo-control module; one prominent sensor visualization region; a health instrument and compact live metrics; a thermal hotspot/statistics module; then health trend, recent events, and system/device status. CSS Grid proportions adapt to the actual viewport instead of hardcoding reference values.

Thermal, Vibration, and Acoustic sections each prioritize their own real metrics and spectra. Events, Machines, Datasets, Devices, and Demo remain available as supported surfaces, but no Settings page is added because the backend exposes no settings contract.

Dataset registry is currently empty in the running environment. Its source controls should show no registered option and preserve the existing optional path-entry capability on the Demo page. The interface must not invent selectable datasets to fill the reference's controls.

## Interaction behavior

- Replace the dominant vertical rail with one compact top navigation row; show a clear active state and preserve keyboard access.
- Keep machine selection and API/WebSocket/demo state in the global shell, but label each state independently.
- Use short pressed/hover/focus feedback for controls. Start/stop controls reflect actual busy and backend-running states.
- Keep dataset inputs empty by default; validate required machine selection and numeric channel/playback input without pretending to validate server filesystem paths.
- Preserve usable local telemetry history and avoid repeating the history REST request for every WebSocket message.
- Use inline loading, empty, partial-data, disconnected, and error states with clear next actions.

## Motion policy

No decorative looping animation, scroll pinning, cinematic reveals, or GSAP-driven dashboard motion. Use short transitions for hover/focus, selected navigation, and state changes. Keep live chart updates non-animated or minimally animated to avoid motion noise, and honor `prefers-reduced-motion`.

## Responsive strategy

- **1920×1080:** reference-like high-density workstation layout with a compact single-row shell and balanced instrument grid.
- **1440×900 / 1366×768:** compact panels and labels, chart regions may reduce height, no horizontal clipping.
- **Tablet:** navigation may wrap or horizontally scroll; major modules reflow into two columns.
- **Mobile:** compact horizontal navigation, one-column panel stack, readable chart/metric labels, controls remain reachable, and wide tables may scroll inside their own region without expanding the page.

## Anti-patterns to avoid

- Vertical sidebar dominating the viewport.
- Light/cream cards, editorial dividers, giant titles, or large empty margins.
- Generic white-card dashboard, excessive radii, floating-card shadows, or ornamental gradients.
- The screenshot's example telemetry, thermal imagery, source names, timestamps, or “System Online” claim copied as data.
- Fake temperature, FPS, frame counts, anomaly score, device connectivity, events, or baseline completion.
- Marking unknown, disconnected, missing, stale, or uncalibrated states green.
- Color-only severity or unlabelled chart axes.
