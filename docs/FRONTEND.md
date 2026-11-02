# Frontend: single-page dashboard

React 19 + TypeScript + Vite. The whole UI is one page, which replays recorded thermal video, vibration and sound
through the backend's models and shows each result separately. Code is in `frontend/`. Project overview and the honesty rules are in
[`PROJECT_GUIDE.md`](PROJECT_GUIDE.md) (§8 covers how the dashboard behaves).

## Layout

```
src/
  App.tsx                         mounts the dashboard
  components/dashboard/
    Dashboard.tsx                 Input, Test window, Output and Model test results panels
    dashboard.css                 page styles (light mode, Bahnschrift with Roboto/Segoe UI fallbacks)
    knownCondition.ts             reads a recording's known label from its name; never guesses one
  services/
    api.ts                        REST client (/api/...)
    useTelemetry.ts               /ws/telemetry WebSocket hook with reconnect
    contracts.ts                  runtime checks on API and telemetry payloads
  types/index.ts                  shared types
```

## Run

```powershell
npm install        # once
npm run dev        # http://localhost:5173 ; needs the backend on port 8000
npm run build      # type-check, then build into dist/
npm run lint       # oxlint
```

The dev server listens on `127.0.0.1` and proxies `/api` and `/ws` to `http://127.0.0.1:8000`
([`frontend/vite.config.ts`](../frontend/vite.config.ts)).

## Backend address

By default every request goes to the page's own origin, so the same build works:
- behind the Vite proxy in development
- when the backend serves `dist/` itself (`IDEALAB_SERVE_FRONTEND_DIR`, used on the Raspberry Pi)
- through the Quick Tunnel and the Render gateway

To call a different backend, set these at build time:

| Variable | Effect |
|---|---|
| `VITE_API_BASE_URL` | base URL for REST calls, for example `https://api.example.com` |
| `VITE_WS_URL` | full telemetry WebSocket URL. If unset, it is derived from `VITE_API_BASE_URL` or the page origin |

## Deploy to the Pi

Build on the development PC (`npm run build`), then copy `dist/` to `~/mmhm-demo/frontend/dist` on the Pi. See
[`PI_DEMO.md`](PI_DEMO.md). The Pi does not run Node.
