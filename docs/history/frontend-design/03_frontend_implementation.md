# Frontend implementation record

## 1. Previous visual problems

The previous implementation read as a light, editorial dashboard: a dominant left rail, pale card surfaces, oversized page heading, generous empty margins, and sparse overview composition. That conflicted with the supplied screenshot's compact horizontal operations console. The earlier styling direction has been discarded wherever it conflicted with the screenshot.

## 2. New design direction

The application now uses **Mission Control / Industrial Monitoring Dashboard** as its primary visual style, supported by **Data-Dense** and **Tactical Enterprise UI**. The decision and token-level guidance are in [02_visual_direction.md](02_visual_direction.md).

The interface uses a blue-black background, compact navy instrumentation panels, fine cool borders, small radii, cyan-blue interaction accents, restrained green/amber/red state semantics, dense technical labels, and minimal motion. It does not copy the reference's sample values, video, timestamps, event rows, or "System Online" assertion. Unknown, absent, or disconnected data remains explicit.

## 3. Information architecture and layout

The dominant left sidebar was replaced with a compact horizontal top bar. It contains the IDEA LAB identity, Thermal/Vibration/Acoustic/Fusion/Events/Machines navigation, a Data menu for Datasets and Devices, active-machine selector, API and WebSocket states, and an amber dataset-demo control. There is no Settings surface because the backend exposes no settings contract.

The Fusion workspace uses the reference's zones: source/demo controls; a prominent sensor visualization region; machine health; live thermal metrics; hotspot analysis; health trend; modality evidence; recent events; hardware/connection status; and demo state. On sparse data, visualization areas retain their size and explain exactly what is awaited. Tablet layouts reflow to two columns; mobile is a single-column stack with a compact wrapped navigation grid and locally scrollable wide dataset rows.

Other supported sections are Thermal, Vibration, Acoustic, Events, Machines, Datasets, Devices, and Demo Controls. Navigation is state-based because the existing application had no routing requirement. A selected-machine context is shared across sections.

## 4. Files created

Page and layout components:

- `frontend/src/components/layout/AppShell.tsx`
- `frontend/src/components/overview/OverviewPage.tsx`
- `frontend/src/components/overview/DataSourcePanel.tsx`
- `frontend/src/components/analytics/AnalyticsPage.tsx`
- `frontend/src/components/events/EventsPage.tsx`
- `frontend/src/components/machines/MachinesPage.tsx`
- `frontend/src/components/datasets/DatasetsPage.tsx`
- `frontend/src/components/devices/DevicesPage.tsx`
- `frontend/src/components/demo/DemoConsole.tsx`

Reusable presentation, charts, and API contracts:

- `frontend/src/components/common/Icon.tsx`
- `frontend/src/components/common/Panel.tsx`
- `frontend/src/components/common/SectionHeading.tsx`
- `frontend/src/components/common/StatusBadge.tsx`
- `frontend/src/components/common/MetricValue.tsx`
- `frontend/src/components/common/DataState.tsx`
- `frontend/src/components/common/EmptyState.tsx`
- `frontend/src/components/common/HealthGauge.tsx`
- `frontend/src/components/charts/TelemetryCharts.tsx`
- `frontend/src/services/contracts.ts`

## 5. Files changed or removed

Changed: `frontend/src/App.tsx` (application orchestration and data lifecycle), `frontend/src/index.css` (dark industrial tokens, compact shell, panels, charts, responsive behavior and focus states), `frontend/src/services/api.ts` (typed REST boundary/error handling), `frontend/src/services/useTelemetry.ts` (validated WebSocket lifecycle), `frontend/src/types/index.ts` (backend-aligned view types), and `frontend/index.html` (product metadata). `frontend/package.json` and its lockfile no longer include unused GSAP packages; the finished interface uses CSS transitions and reduced-motion handling instead.

The prior Vite mark and one-off dashboard components were removed: `frontend/src/assets/vite.svg`, `BandEnergyChart.tsx`, `ConnectionBadge.tsx`, `DemoPanel.tsx`, `EventTimeline.tsx`, `HealthTrendChart.tsx`, `ModalityDetails.tsx`, and `SpectralPeaksChart.tsx`. Their responsibilities are now covered by the new domain/page components and shared chart/presentation primitives. Inert motion data attributes from the prior visual pass were removed. No backend, ML, signal-processing, dataset, or migration source was changed.

## 6. API and telemetry behavior preserved

The UI uses the repository's actual REST methods for health, machine listing/creation/detail/status/history/events, datasets, devices, and global demo status/start/stop. It does not add routes or alter backend behavior. API errors remain visible as data states, rather than being converted into plausible-looking values.

The backend WebSocket is a global broadcast at `/ws/telemetry`; the hook validates messages and filters by the selected `machine_id` in the client. It handles text, Blob, ArrayBuffer, and typed-array data; exposes connecting/open/reconnecting/closed/error; retries with bounded exponential backoff; and clears timers/sockets during cleanup. An open socket without an accepted envelope is shown as **Awaiting envelope**, not live telemetry.

`App.tsx` requests history when the selected machine changes, sorts valid history chronologically, reconciles incoming health samples by timestamp, and caps local series at 240 points. It does not refetch the full history endpoint on each telemetry tick. Persisted events are fetched on machine selection and refreshed only when backend event-start/event-clear messages arrive. Demo status is polled at five-second intervals because it is a global REST state; datasets and devices are not polled on telemetry ticks.

## 7. Health and modality semantics

- Backend `normal`, `warning`, `critical`, and `unknown` are not recomputed or reclassified in the UI.
- A null score remains unavailable; the gauge does not invent a zero or healthy value.
- Confidence is shown as backend-reported evidence coverage, not a probability.
- Modality contributions, evidence, and missing-modality lists are displayed only when supplied by backend output. Not reported is not drawn as zero.
- The baseline field is shown as a record/status, not proof that all modalities have enough calibrated evidence.
- Vibration, acoustic, and thermal analysis use actual provided features. No waveform, spectrogram, or synthetic trend is drawn.
- Current thermal fields describe relative intensity/hotspot features. The UI does not infer °C or create a thermal frame; the API does not deliver an image/frame field.
- Hardware `not_connected` stays disconnected. API response, WebSocket connection, modality data availability, and demo-session state are independent indicators.
- A dataset session is labelled as dataset/demo only when the backend reports a running demo or the received envelope identifies demo mode.

## 8. Demo and data availability behavior

The Demo Controls page consumes the backend's `/api/demo/scenarios` registry when available and presents its thermal, vibration, and acoustic presets by their server-provided labels and notes. Preset selection passes the source and, for vibration, the backend-provided channel and optional file range. Custom source paths remain available, with suggestions from the dataset registry where present; custom vibration ranges are checked for non-negative integer values and ordered bounds. If the scenario endpoint is unavailable, the UI reports that state while retaining the custom-path workflow. Preset registration is not treated as proof that a local file is currently readable: final validation remains with the backend.

The local start-form validation was exercised with no source path and correctly prevented the request with an explanatory message. Demo start and stop were not run end-to-end: no dataset was registered and no real source path was available, and creating a session with guessed paths would not be meaningful verification.

## 9. Screenshot comparison and refinement passes

The supplied screenshot was opened and compared with the running application. The comparison focused on shell orientation, panel density/proportions, navy palette, typography scale, grid/border language, state indicators, charts, and source controls. The first implementation capture (`artifacts/screenshots/01_pass1_1920x1080.png`) showed that the machine-heading/empty-state treatment and grid rhythm still needed tightening. Subsequent passes compacted the heading and controls, made the four-row Fusion composition explicit, tightened empty-state typography, and added a low-height desktop grid so 1366×768 did not collapse or overlap. Mobile navigation was changed from a clipped/scrolled strip to a wrapped four-column grid.

Final captures were opened and inspected at all required sizes:

- [1920×1080 final](screenshots/04_final_1920x1080.png)
- [1440×900 final](screenshots/05_final_1440x900.png)
- [1366×768 final](screenshots/06_final_1366x768.png)
- [390×844 mobile final](screenshots/07_final_mobile_390x844.png)

The current screen matches the reference's dark console, horizontal navigation, compact instrumentation panels, semantic status, and dense multi-zone composition. It is not a pixel/data clone: the reference shows a thermal image and populated trends, while this backend runtime has no thermal frame or telemetry envelope. The implementation correctly shows a gridded waiting state instead. The 1920 capture shows the actual selected machine, unknown health/no score, zero valid history, empty dataset registry, one of three probes connected, API responding, WebSocket open/awaiting, and demo idle. No reference telemetry was copied.

## 10. Responsive and accessibility work

The responsive checks use explicit 1920×1080, 1440×900, 1366×768, and 390×844 captures plus viewport/DOM geometry checks. At mobile width the document and body widths stayed within the viewport; no visible component extended past the viewport bounds. Wide dataset provenance rows may scroll inside their own region instead of expanding the page. Fusion panels stack at mobile widths, while desktop remains a dense control-room layout.

The shell includes a skip link, semantic header/nav/main landmarks, active `aria-current`, labelled machine/dataset inputs, keyboard-operable controls, focus-visible rings, state text as well as color, chart descriptions/empty states, and `prefers-reduced-motion` rules. Machine/event/dataset/device pages provide loading, error, empty, and no-selection states.

## 11. Performance and implementation decisions

- REST history is not polled per WebSocket envelope; local history and telemetry chart data are bounded to 240 samples.
- WebSocket payloads are validated before entering state; stale callbacks, machine mismatch, malformed messages, reconnection, and cleanup are handled explicitly.
- Events are not refetched on every telemetry update; they refresh on persisted transition messages.
- Recharts remains the chart library; no new visualization or UI framework was installed for this rebuild.
- GSAP and its React adapter were removed because the finished interface does not use them.
- The demo form uses the selected machine as its React key instead of mirroring that prop through an effect, avoiding an unnecessary state-sync render when machine context changes.
- All dashboard panels avoid decorative looping animation. CSS respects reduced motion.
- `npm run build` emits a Vite chunk-size advisory because the charting/application bundle exceeds Vite's default 500 kB warning threshold; the build still succeeds. This remains a later bundle-splitting opportunity.

## 12. Functional verification performed

Verified in the local browser/API runtime:

- frontend loads at `http://127.0.0.1:5173/`; API health responds and the shell displays API ready;
- a fresh post-build browser load settles with API ready, WebSocket open/awaiting, and no console error or warning entries;
- WebSocket opens and correctly remains in the waiting-for-first-envelope state;
- machine selector changes selected machine and updates its returned health/baseline/evidence state;
- Thermal, Vibration, Acoustic, Fusion, Events, Machines, Datasets, Devices, and Demo Controls navigation renders;
- events and datasets display truthful empty states;
- devices reflect the API's actual statuses, including thermal camera connected and vibration sensor/microphone not connected;
- demo controls show idle/disabled state and reject a source-less start before sending a request;
- health-history empty state, no-frame thermal state, and modality-missing states render without crashing;
- mobile DOM has no document-level horizontal overflow; final screenshots visually confirm the tested viewport layouts.

Not claimed as verified: a live telemetry envelope/update, chart samples, populated event rows, dataset selection, actual demo start/stop, or backend-induced WebSocket disconnect. The verified backend state contains no active telemetry producer, no registered datasets, and no valid health samples for the selected machine. No backend endpoint was changed to facilitate these tests.

## 13. Build and lint results

Commands run from `frontend/`:

- `npm run build` — passed (`tsc -b` and Vite build); output was 692.41 kB JavaScript (199.23 kB gzip) and 54.45 kB CSS (11.02 kB gzip). Vite emitted its advisory that a minified chunk exceeds the default 500 kB threshold.
- `npm run lint` — completed with no errors and four `react(set-state-in-effect)` warnings: one in `useTelemetry.ts` and three in `App.tsx`. They occur in the WebSocket lifecycle and selected-machine data lifecycle; they remain for a deliberate follow-up rather than being hidden with suppressions.
- `git diff --check` — passed; Git printed only its existing LF/CRLF working-copy notices.

The package defines no frontend `test` script. No frontend unit-test suite was available to run. `git diff --check` is also included in the final verification pass.

## 14. Local run commands

From the repository root, start the backend in one terminal:

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Start the frontend in a second terminal:

```powershell
cd frontend
npm run dev
```

The current Vite proxy targets the local backend; see `frontend/vite.config.ts` for the development proxy configuration. Dependencies were already present; no package installation was performed for this visual rebuild.

## 15. Git/worktree status

The current branch is `main`. Frontend implementation files and artifacts remain uncommitted in the worktree. Changes are confined to frontend code/dependency metadata and `artifacts/`; no backend/ML/data source file appears in the changed-file list. Existing changes were preserved; no reset, checkout, or discard operation was used.

## 16. Known limitations and backend-dependent opportunities

- No thermal frame/image, calibrated temperature, continuous telemetry envelope, or valid health-history sample was available during verification. The corresponding dashboard visuals are truthful empty/waiting states.
- The dataset registry is empty in the current runtime. Actual demo playback, source selection, and stop behavior cannot be verified until a real supported dataset/path is provided.
- A green UI may not imply healthy machinery: API responding only describes REST reachability; the WebSocket can be open while awaiting data; hardware probes and backend health remain separate.
- The backend's WebSocket is global, so client-side machine filtering does not reduce server broadcast volume.
- Calibration/reset actions, sensor pairing, radiometric temperature, per-modality freshness, active anomaly state/history, and thermal frames would require backend support before the frontend can expose them truthfully.
- The production bundle exceeds Vite's default chunk advisory threshold; route/page-level lazy loading or chart splitting may help if bundle budgets become strict.
