// Stable public address for the Raspberry Pi demo.
//
// Render serves this tiny reverse proxy at a fixed URL (https://<service>.onrender.com). Every request - pages, API
// calls, the thermal video stream and the /ws/telemetry WebSocket - is forwarded to whatever Cloudflare Quick Tunnel
// the Pi is currently running. The Quick Tunnel URL changes on every restart, so the Pi registers its new URL here
// (POST /__tunnel with the shared token) and re-registers every few minutes while the tunnel is up.
//
// No dependencies: Node's built-in http/https only. Node 18+.
"use strict";

const http = require("http");
const https = require("https");
const crypto = require("crypto");

const PORT = Number(process.env.PORT || 10000);
const REGISTER_TOKEN = process.env.REGISTER_TOKEN || "";
// Only Quick Tunnel URLs can be registered, so a leaked token cannot turn this into an open proxy to other hosts.
const TUNNEL_RE = /^https:\/\/[a-z0-9-]+\.trycloudflare\.com$/;
const UPSTREAM_TIMEOUT_MS = 30000;
const HOP_BY_HOP = new Set([
  "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
  "te", "trailer", "transfer-encoding", "upgrade", "host",
]);

let target = null; // URL of the current tunnel, or null when the demo is offline
let updatedAt = null;
setTarget(process.env.TUNNEL_URL || "");

function setTarget(raw) {
  const value = String(raw || "").trim().replace(/\/+$/, "");
  if (!value) { target = null; updatedAt = new Date().toISOString(); return true; }
  if (!TUNNEL_RE.test(value)) return false;
  target = new URL(value);
  updatedAt = new Date().toISOString();
  return true;
}

function tokenOk(header) {
  if (!REGISTER_TOKEN) return false;
  const given = Buffer.from(String(header || "").replace(/^Bearer\s+/i, ""));
  const expected = Buffer.from(REGISTER_TOKEN);
  return given.length === expected.length && crypto.timingSafeEqual(given, expected);
}

function offlinePage(res, status) {
  const body = `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Demo offline</title>
<meta http-equiv="refresh" content="20">
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#f6f7f9;color:#1f2933;
font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}main{max-width:32rem;padding:2rem 16px;text-align:center}
h1{font-size:1.4rem;margin:0 0 .5rem}p{margin:.25rem 0;color:#52606d}</style></head><body><main>
<h1>Machine Health Monitoring demo is offline</h1>
<p>The Raspberry Pi that runs the demo is not connected right now.</p>
<p>This page checks again every 20 seconds.</p></main></body></html>`;
  res.writeHead(status, { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" });
  res.end(body);
}

function forwardHeaders(req) {
  const headers = {};
  for (const [name, value] of Object.entries(req.headers)) {
    if (!HOP_BY_HOP.has(name)) headers[name] = value;
  }
  headers.host = target.host;
  headers["x-forwarded-host"] = req.headers.host || "";
  headers["x-forwarded-proto"] = "https";
  return headers;
}

function handleRegister(req, res) {
  if (!tokenOk(req.headers.authorization)) { res.writeHead(401).end("unauthorized\n"); return; }
  let body = "";
  req.setEncoding("utf8");
  req.on("data", (chunk) => {
    body += chunk;
    if (body.length > 1024) req.destroy();
  });
  req.on("end", () => {
    let url = "";
    try { url = JSON.parse(body || "{}").url || ""; } catch { res.writeHead(400).end("body must be JSON {\"url\": ...}\n"); return; }
    if (!setTarget(url)) { res.writeHead(400).end("url must look like https://<name>.trycloudflare.com\n"); return; }
    console.log(`tunnel ${target ? "registered" : "cleared"} at ${updatedAt}`);
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ online: Boolean(target), updatedAt }) + "\n");
  });
}

const server = http.createServer((req, res) => {
  if (req.url === "/__tunnel" && req.method === "POST") return handleRegister(req, res);
  if (req.url === "/__tunnel/status") {
    res.writeHead(200, { "content-type": "application/json", "cache-control": "no-store" });
    return res.end(JSON.stringify({ online: Boolean(target), updatedAt }) + "\n");
  }
  if (req.url === "/healthz") { res.writeHead(200).end("ok\n"); return; } // Render health check; independent of the Pi
  if (!target) return offlinePage(res, 503);

  const upstream = https.request({
    hostname: target.hostname, port: 443, method: req.method, path: req.url,
    headers: forwardHeaders(req), timeout: UPSTREAM_TIMEOUT_MS,
  }, (up) => {
    // 530 is Cloudflare's answer when the tunnel behind the hostname is gone.
    if (up.statusCode === 530) { up.resume(); return offlinePage(res, 503); }
    const headers = { ...up.headers };
    for (const name of HOP_BY_HOP) delete headers[name];
    if (headers.location) headers.location = String(headers.location).replace(target.origin, "");
    res.writeHead(up.statusCode, up.statusMessage, headers);
    up.pipe(res);
  });
  upstream.on("timeout", () => upstream.destroy(new Error("upstream timeout")));
  upstream.on("error", (err) => {
    console.warn(`proxy error ${req.method} ${req.url}: ${err.message}`);
    if (!res.headersSent) offlinePage(res, 502); else res.destroy();
  });
  req.pipe(upstream);
});

// WebSocket (live telemetry): forward the upgrade, then splice the two sockets together.
server.on("upgrade", (req, socket, head) => {
  if (!target) { socket.end("HTTP/1.1 503 Service Unavailable\r\n\r\n"); return; }
  const headers = forwardHeaders(req);
  headers.connection = "Upgrade";
  headers.upgrade = req.headers.upgrade || "websocket";
  const upstream = https.request({ hostname: target.hostname, port: 443, method: req.method, path: req.url, headers });
  upstream.on("upgrade", (up, upSocket, upHead) => {
    let reply = `HTTP/1.1 ${up.statusCode} ${up.statusMessage}\r\n`;
    for (let i = 0; i < up.rawHeaders.length; i += 2) reply += `${up.rawHeaders[i]}: ${up.rawHeaders[i + 1]}\r\n`;
    socket.write(reply + "\r\n");
    if (upHead && upHead.length) socket.write(upHead);
    if (head && head.length) upSocket.write(head);
    upSocket.pipe(socket).pipe(upSocket);
    const close = () => { socket.destroy(); upSocket.destroy(); };
    socket.on("error", close); upSocket.on("error", close);
    socket.on("close", close); upSocket.on("close", close);
  });
  upstream.on("response", (up) => { // upstream refused the upgrade
    socket.end(`HTTP/1.1 ${up.statusCode} ${up.statusMessage}\r\n\r\n`);
    up.resume();
  });
  upstream.on("error", () => socket.destroy());
  socket.on("error", () => upstream.destroy());
  upstream.end();
});

server.listen(PORT, () => {
  console.log(`listening on :${PORT}; tunnel ${target ? "set from TUNNEL_URL" : "not set yet"}; registration ${REGISTER_TOKEN ? "enabled" : "DISABLED (no REGISTER_TOKEN)"}`);
});
