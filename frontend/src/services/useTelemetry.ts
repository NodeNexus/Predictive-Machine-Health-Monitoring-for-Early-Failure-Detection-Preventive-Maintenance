import { useCallback, useEffect, useRef, useState } from "react";
import { ContractError, parseTelemetryMessage } from "./contracts";
import { apiBaseUrl } from "./api";
import type { TelemetryPayload } from "../types";

export type ConnectionState = "connecting" | "open" | "reconnecting" | "closed" | "error";

export interface UseTelemetryOptions {
  /** Broadcast telemetry is filtered client-side because the backend socket is global. */
  machineId?: string | null;
  enabled?: boolean;
  url?: string;
  reconnect?: boolean;
  /** Number of retries after the first connection attempt. Defaults to unlimited. */
  maxReconnectAttempts?: number;
  reconnectInitialDelayMs?: number;
  reconnectMaxDelayMs?: number;
}

export type TelemetryErrorKind = "socket" | "invalid_payload" | "unsupported_message" | "reconnect_exhausted";

export class TelemetryError extends Error {
  readonly name = "TelemetryError";
  readonly kind: TelemetryErrorKind;
  readonly cause: unknown;

  constructor(kind: TelemetryErrorKind, message: string, cause?: unknown) {
    super(message);
    this.kind = kind;
    this.cause = cause;
  }
}

export interface UseTelemetryResult {
  connection: ConnectionState;
  latest: TelemetryPayload | null;
  /** Epoch milliseconds for the last accepted payload, not the backend timestamp. */
  lastMessageAt: number | null;
  error: TelemetryError | null;
  /** Number of attempts made since the last successful connection. */
  reconnectAttempt: number;
  reconnect: () => void;
  close: () => void;
}

function telemetryUrl(explicitUrl?: string): string {
  const configured = explicitUrl ?? (import.meta.env.VITE_WS_URL as string | undefined);
  if (configured) return configured;

  if (apiBaseUrl) {
    const wsProtocol = apiBaseUrl.startsWith("https") ? "wss" : "ws";
    const hostAndPath = apiBaseUrl.replace(/^https?:\/\//, "");
    return `${wsProtocol}://${hostAndPath}/ws/telemetry`;
  }

  if (typeof window === "undefined") return "/ws/telemetry";
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${window.location.host}/ws/telemetry`;
}

function reconnectDelay(attempt: number, initial: number, maximum: number): number {
  return Math.min(maximum, initial * 2 ** Math.max(0, attempt - 1));
}

async function decodeSocketData(data: unknown): Promise<string> {
  if (typeof data === "string") return data;
  if (typeof Blob !== "undefined" && data instanceof Blob) return data.text();
  if (data instanceof ArrayBuffer) return new TextDecoder().decode(data);
  if (ArrayBuffer.isView(data)) {
    const bytes = new Uint8Array(data.buffer, data.byteOffset, data.byteLength);
    return new TextDecoder().decode(bytes);
  }
  throw new TelemetryError("unsupported_message", "Telemetry socket sent an unsupported message type");
}

/**
 * Maintain one validated, reconnecting subscription to the backend's global
 * telemetry broadcast. The hook never fabricates a value for a malformed or
 * machine-mismatched payload.
 */
export function useTelemetry(options: UseTelemetryOptions = {}): UseTelemetryResult {
  const {
    machineId = null,
    enabled = true,
    url,
    reconnect = true,
    maxReconnectAttempts = Number.POSITIVE_INFINITY,
    reconnectInitialDelayMs = 500,
    reconnectMaxDelayMs = 15_000,
  } = options;

  const [connection, setConnection] = useState<ConnectionState>(enabled ? "connecting" : "closed");
  const [latest, setLatest] = useState<TelemetryPayload | null>(null);
  const [lastMessageAt, setLastMessageAt] = useState<number | null>(null);
  const [error, setError] = useState<TelemetryError | null>(null);
  const [reconnectAttempt, setReconnectAttempt] = useState(0);
  const [reconnectNonce, setReconnectNonce] = useState(0);

  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const manualCloseRef = useRef(false);
  const reconnectAttemptRef = useRef(0);
  const previousScopeRef = useRef<string | null>(null);

  const reconnectNow = useCallback(() => {
    manualCloseRef.current = false;
    setReconnectNonce((value) => value + 1);
  }, []);

  const close = useCallback(() => {
    manualCloseRef.current = true;
    if (reconnectTimerRef.current !== null) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    socketRef.current?.close();
    socketRef.current = null;
    setConnection("closed");
  }, []);

  useEffect(() => {
    const scope = `${machineId ?? "*"}|${url ?? ""}|${enabled ? "enabled" : "disabled"}`;
    if (previousScopeRef.current !== scope) {
      setLatest(null);
      setLastMessageAt(null);
      previousScopeRef.current = scope;
    }

    let disposed = false;
    manualCloseRef.current = false;
    reconnectAttemptRef.current = 0;
    setReconnectAttempt(0);
    setError(null);

    const clearReconnectTimer = () => {
      if (reconnectTimerRef.current !== null) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
    };

    if (!enabled) {
      setConnection("closed");
      return () => {
        disposed = true;
        clearReconnectTimer();
        socketRef.current?.close();
        socketRef.current = null;
      };
    }

    const scheduleReconnect = () => {
      if (disposed || manualCloseRef.current || !reconnect) {
        setConnection("closed");
        return;
      }

      const nextAttempt = reconnectAttemptRef.current + 1;
      if (nextAttempt > maxReconnectAttempts) {
        const exhausted = new TelemetryError(
          "reconnect_exhausted",
          "Telemetry connection retries exhausted",
        );
        setError(exhausted);
        setConnection("closed");
        return;
      }

      reconnectAttemptRef.current = nextAttempt;
      setReconnectAttempt(nextAttempt);
      setConnection("reconnecting");
      clearReconnectTimer();
      reconnectTimerRef.current = setTimeout(() => {
        reconnectTimerRef.current = null;
        openSocket();
      }, reconnectDelay(nextAttempt, reconnectInitialDelayMs, reconnectMaxDelayMs));
    };

    const openSocket = () => {
      if (disposed || manualCloseRef.current) return;
      setConnection(reconnectAttemptRef.current > 0 ? "reconnecting" : "connecting");
      clearReconnectTimer();

      let socket: WebSocket;
      try {
        socket = new WebSocket(telemetryUrl(url));
      } catch (cause) {
        const socketError = new TelemetryError("socket", "Unable to open telemetry connection", cause);
        setError(socketError);
        scheduleReconnect();
        return;
      }

      socketRef.current = socket;
      socket.onopen = () => {
        if (disposed || socketRef.current !== socket) return;
        reconnectAttemptRef.current = 0;
        setReconnectAttempt(0);
        setConnection("open");
        setError(null);
      };
      socket.onmessage = (event) => {
        if (disposed || socketRef.current !== socket) return;
        void (async () => {
          try {
            const payload = parseTelemetryMessage(await decodeSocketData(event.data));
            if (disposed || socketRef.current !== socket) return;
            if (machineId !== null && payload.machine_id !== machineId) return;
            setLatest(payload);
            setLastMessageAt(Date.now());
            setError(null);
          } catch (cause) {
            if (disposed || socketRef.current !== socket) return;
            const message =
              cause instanceof ContractError ? `Invalid telemetry payload: ${cause.message}` : "Invalid telemetry payload";
            setError(new TelemetryError("invalid_payload", message, cause));
            // Keep the socket open: a single bad broadcast must not take down live monitoring.
          }
        })();
      };
      socket.onerror = () => {
        if (disposed || socketRef.current !== socket) return;
        setError(new TelemetryError("socket", "Telemetry connection encountered an error"));
        setConnection("error");
        // Browsers normally follow `error` with `close`, but closing here and
        // scheduling explicitly also handles WebSocket implementations that
        // emit an error without a subsequent close event.
        socketRef.current = null;
        socket.close();
        scheduleReconnect();
      };
      socket.onclose = () => {
        if (disposed || socketRef.current !== socket) return;
        socketRef.current = null;
        scheduleReconnect();
      };
    };

    openSocket();

    return () => {
      disposed = true;
      clearReconnectTimer();
      if (socketRef.current !== null) {
        const socket = socketRef.current;
        socketRef.current = null;
        socket.close();
      }
    };
  }, [
    enabled,
    machineId,
    maxReconnectAttempts,
    reconnect,
    reconnectInitialDelayMs,
    reconnectMaxDelayMs,
    reconnectNonce,
    url,
  ]);

  return {
    connection,
    latest,
    lastMessageAt,
    error,
    reconnectAttempt,
    reconnect: reconnectNow,
    close,
  };
}
