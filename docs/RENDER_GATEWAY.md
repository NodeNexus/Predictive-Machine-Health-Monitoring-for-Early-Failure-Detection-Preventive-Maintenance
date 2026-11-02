# Render gateway: one stable URL for the Pi demo

The Quick Tunnel URL (`https://<random>.trycloudflare.com`) changes on every restart of the Pi demo. This folder is
a small Node proxy for Render's free tier. It gives the demo a fixed address such as `https://mmhm-demo.onrender.com`
and forwards every request to whatever tunnel the Pi is running at that moment. That covers the dashboard, the API,
the thermal video and the `/ws/telemetry` WebSocket. The browser address bar keeps showing the Render URL.

```
browser ──► https://mmhm-demo.onrender.com ──► https://<current>.trycloudflare.com ──► Pi backend (127.0.0.1)
                    ▲
                    └── Pi: POST /__tunnel {url}  (on start, then every 4 min)
```

- `server.js` has no dependencies and needs Node 18 or later.
- Only `https://<name>.trycloudflare.com` URLs can be registered, so the gateway cannot be pointed anywhere else.
- When the Pi is stopped or unreachable, visitors get a "demo offline" page that refreshes every 20 s.
- **No authentication:** anyone with the Render URL can use the dashboard, including its Start/Stop controls. This is
  the same as the Quick Tunnel URL.

## 1. Create the Render service

1. Push this repository, including `deploy/render/`, to GitHub.
2. In Render, go to **New → Blueprint**, pick the repository and set **Blueprint Path** to `deploy/render/render.yaml`.
   - The service name in that file (`mmhm-demo`) becomes the URL. If the name is taken, change it.
   - Alternatively, use **New → Web Service** with these settings:
     - Root Directory: `deploy/render`
     - Runtime: Node
     - Build command: `echo no build needed`
     - Start command: `node server.js`
     - Health check path: `/healthz`
     - Environment variable: `REGISTER_TOKEN` set to a long random string
3. After the first deploy, open the service's **Environment** tab and copy `REGISTER_TOKEN`.

## 2. Tell the Pi about it

On the Pi, run this once:

```bash
cd ~/mmhm-demo
umask 077
cat > .run/render.env <<'EOF'
RENDER_GATEWAY_URL=https://mmhm-demo.onrender.com
RENDER_TOKEN=paste-the-token-here
EOF
bash deploy/pi/start.sh
```

From then on:
- `start.sh` registers the new tunnel and prints the stable URL next to the tunnel URL.
- `status.sh` shows the sync loop.
- `stop.sh` switches the gateway to the offline page.

`.run/` is git-ignored, so the token never reaches the repository.

## Free-tier notes

- A free Render service sleeps after 15 minutes without traffic, and the first visit after that waits about a minute.
  - While the demo runs, the Pi's re-registration every 4 minutes keeps the service awake.
  - Running it all the time uses about 744 of the 750 free instance hours per month. Stop the demo when it is not
    needed.
- The registered URL is kept in memory. After a Render restart or redeploy, the gateway shows the offline page until
  the Pi's next re-registration, which is at most 4 minutes away.

## Test locally

```bash
PORT=18555 REGISTER_TOKEN=test node deploy/render/server.js
curl -X POST -H 'Authorization: Bearer test' -d '{"url":"https://<current>.trycloudflare.com"}' http://127.0.0.1:18555/__tunnel
# open http://127.0.0.1:18555
```
