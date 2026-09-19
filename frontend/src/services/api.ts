import {
  ContractError,
  parseAnomalyEvents,
  parseDatasets,
  parseDemoScenarios,
  parseDemoStatus,
  parseDevices,
  parseHealthHistory,
  parseHealthResponse,
  parseMachine,
  parseMachineHealthState,
  parseMachineVideos,
  parseThermalFeed,
} from "./contracts";
import type {
  AnomalyEventRecord,
  DatasetInfo,
  DemoScenario,
  DemoStartRequest,
  DemoStatus,
  DeviceStatus,
  HealthHistoryPoint,
  HealthResponse,
  Machine,
  MachineCreate,
  MachineHealthState,
  MachineVideoEntry,
  ThermalFeedEntry,
} from "../types";

export type ApiErrorKind = "http" | "network" | "timeout" | "invalid_json" | "invalid_response";

export interface ApiRequestOptions extends RequestInit {
  /** Optional client-side timeout. A caller-provided AbortSignal is always respected. */
  timeoutMs?: number;
}

export interface CollectionRequestOptions extends ApiRequestOptions {
  limit?: number;
}

export class ApiError extends Error {
  readonly name = "ApiError";
  readonly kind: ApiErrorKind;
  readonly details: {
    status?: number;
    statusText?: string;
    method: string;
    path: string;
    detail?: string | null;
    payload?: unknown;
    cause?: unknown;
  };

  constructor(
    kind: ApiErrorKind,
    message: string,
    details: {
      status?: number;
      statusText?: string;
      method: string;
      path: string;
      detail?: string | null;
      payload?: unknown;
      cause?: unknown;
    },
  ) {
    super(message);
    this.kind = kind;
    this.details = details;
  }

  get status(): number | undefined {
    return this.details.status;
  }

  get statusText(): string | undefined {
    return this.details.statusText;
  }

  get method(): string {
    return this.details.method;
  }

  get path(): string {
    return this.details.path;
  }

  get detail(): string | null | undefined {
    return this.details.detail;
  }

  get payload(): unknown {
    return this.details.payload;
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

/** Keep AbortError distinguishable from an unavailable backend. */
export function isAbortError(error: unknown): boolean {
  return (
    (typeof DOMException !== "undefined" && error instanceof DOMException && error.name === "AbortError") ||
    (error instanceof Error && error.name === "AbortError") ||
    (typeof error === "object" && error !== null && "name" in error && (error as { name?: unknown }).name === "AbortError")
  );
}

function isTimeoutError(error: unknown): boolean {
  return typeof DOMException !== "undefined" && error instanceof DOMException && error.name === "TimeoutError";
}

export const apiBaseUrl = (() => {
  const configured = import.meta.env.VITE_API_BASE_URL as string | undefined;
  return configured?.replace(/\/$/, "") ?? "";
})();

function requestUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  if (!apiBaseUrl) return path;
  return `${apiBaseUrl}${path.startsWith("/") ? path : `/${path}`}`;
}

/**
 * URL for the currently active demo session's thermal source, for a
 * browser <video> element - not a fetch() call, since <video src> needs a
 * direct URL. Resolved the same way every other API path is (respects
 * VITE_API_BASE_URL), so it works identically in dev (behind Vite's proxy)
 * and in a built deployment.
 */
export function thermalVideoUrl(): string {
  return requestUrl("/api/demo/thermal-video");
}

/** URL for one curated Thermal V1 dataset feed image, for a plain <img>
 * element - not a fetch() call, for the same reason as thermalVideoUrl. */
export function thermalFeedImageUrl(imageId: string): string {
  return requestUrl(`/api/demo/thermal-image-feed/${encodeURIComponent(imageId)}`);
}

function extractDetail(payload: unknown): string | null {
  if (typeof payload === "string" && payload.trim()) return payload;
  if (typeof payload !== "object" || payload === null) return null;
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (typeof item === "object" && item !== null && "msg" in item) {
          const message = (item as { msg?: unknown }).msg;
          return typeof message === "string" ? message : null;
        }
        return null;
      })
      .filter((item): item is string => item !== null);
    return messages.length > 0 ? messages.join("; ") : null;
  }
  return null;
}

function parseResponseBody(text: string, path: string, method: string, status: number): unknown {
  if (!text.trim()) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch (cause) {
    throw new ApiError("invalid_json", `${method} ${path} returned invalid JSON`, {
      status,
      method,
      path,
      cause,
    });
  }
}

function withTimeout(options: ApiRequestOptions): {
  request: RequestInit;
  cleanup: () => void;
  timedOut: () => boolean;
} {
  const { timeoutMs, ...init } = options;
  if (timeoutMs == null || timeoutMs <= 0) {
    return { request: init, cleanup: () => undefined, timedOut: () => false };
  }

  const controller = new AbortController();
  const callerSignal = init.signal;
  let timeoutHandle: ReturnType<typeof setTimeout> | undefined;
  let didTimeout = false;
  const abortFromCaller = () => controller.abort(callerSignal?.reason);

  if (callerSignal?.aborted) controller.abort(callerSignal.reason);
  else callerSignal?.addEventListener("abort", abortFromCaller, { once: true });

  timeoutHandle = setTimeout(() => {
    didTimeout = true;
    controller.abort(new DOMException("The request timed out", "TimeoutError"));
  }, timeoutMs);

  return {
    request: { ...init, signal: controller.signal },
    cleanup: () => {
      if (timeoutHandle !== undefined) clearTimeout(timeoutHandle);
      callerSignal?.removeEventListener("abort", abortFromCaller);
    },
    timedOut: () => didTimeout,
  };
}

/**
 * Typed JSON request boundary. Callers can cancel with `signal`; cancellation
 * is intentionally rethrown as AbortError so React effects can ignore it.
 */
export async function request<T>(
  path: string,
  options: ApiRequestOptions = {},
  parser?: (value: unknown) => T,
): Promise<T> {
  const method = options.method ?? "GET";
  const { request: fetchOptions, cleanup, timedOut } = withTimeout(options);
  const headers = new Headers(fetchOptions.headers);
  if (!headers.has("Accept")) headers.set("Accept", "application/json");
  if (fetchOptions.body != null && !(fetchOptions.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  try {
    const response = await fetch(requestUrl(path), { ...fetchOptions, headers });
    const text = await response.text();
    let payload: unknown;
    try {
      payload = parseResponseBody(text, path, method, response.status);
    } catch (error) {
      // A proxy/load balancer may return plain text for a failed request. Keep
      // the HTTP status and useful body instead of reporting only bad JSON.
      if (!response.ok && error instanceof ApiError && error.kind === "invalid_json") {
        throw new ApiError("http", text.trim() || `${method} ${path} failed with ${response.status}`, {
          status: response.status,
          statusText: response.statusText,
          method,
          path,
          detail: text.trim() || null,
          payload: text,
          cause: error,
        });
      }
      throw error;
    }

    if (!response.ok) {
      const detail = extractDetail(payload);
      throw new ApiError("http", detail ?? `${method} ${path} failed with ${response.status}`, {
        status: response.status,
        statusText: response.statusText,
        method,
        path,
        detail,
        payload,
      });
    }

    if (parser == null) return payload as T;
    try {
      return parser(payload);
    } catch (cause) {
      if (cause instanceof ContractError) {
        throw new ApiError("invalid_response", `${method} ${path} returned an invalid response`, {
          status: response.status,
          statusText: response.statusText,
          method,
          path,
          detail: cause.message,
          payload,
          cause,
        });
      }
      throw cause;
    }
  } catch (error) {
    if (timedOut()) {
      throw new ApiError("timeout", `${method} ${path} timed out`, {
        method,
        path,
        cause: error,
      });
    }
    if (isAbortError(error)) throw error;
    if (error instanceof ApiError) throw error;
    if (isTimeoutError(error)) {
      throw new ApiError("timeout", `${method} ${path} timed out`, {
        method,
        path,
        cause: error,
      });
    }
    throw new ApiError("network", `${method} ${path} could not be reached`, {
      method,
      path,
      cause: error,
    });
  } finally {
    cleanup();
  }
}

function collectionPath(path: string, options?: CollectionRequestOptions): string {
  if (options?.limit == null) return path;
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}limit=${encodeURIComponent(String(options.limit))}`;
}

function withoutLimit(options?: CollectionRequestOptions): ApiRequestOptions | undefined {
  if (!options) return undefined;
  const requestOptions: ApiRequestOptions & { limit?: number } = { ...options };
  delete requestOptions.limit;
  return requestOptions;
}

export const api = {
  health: (options?: ApiRequestOptions) => request<HealthResponse>("/api/health", options, parseHealthResponse),

  listMachines: (options?: ApiRequestOptions) =>
    request<Machine[]>("/api/machines", options, (value) => {
      if (!Array.isArray(value)) throw new ContractError("machines", "an array", value);
      return value.map((item, index) => parseMachineAt(item, index));
    }),

  createMachine: (body: MachineCreate, options?: ApiRequestOptions) =>
    request<Machine>("/api/machines", { ...options, method: "POST", body: JSON.stringify(body) }, parseMachine),

  getMachine: (id: string, options?: ApiRequestOptions) =>
    request<Machine>(`/api/machines/${encodeURIComponent(id)}`, options, parseMachine),

  machineStatus: (id: string, options?: ApiRequestOptions) =>
    request<MachineHealthState>(`/api/machines/${encodeURIComponent(id)}/status`, options, parseMachineHealthState),

  machineHistory: (id: string, options?: CollectionRequestOptions) =>
    request<HealthHistoryPoint[]>(
      collectionPath(`/api/machines/${encodeURIComponent(id)}/history`, options),
      withoutLimit(options),
      parseHealthHistory,
    ),

  machineEvents: (id: string, options?: CollectionRequestOptions) =>
    request<AnomalyEventRecord[]>(
      collectionPath(`/api/machines/${encodeURIComponent(id)}/events`, options),
      withoutLimit(options),
      parseAnomalyEvents,
    ),

  listDatasets: (options?: ApiRequestOptions) => request<DatasetInfo[]>("/api/datasets", options, parseDatasets),

  listDevices: (options?: ApiRequestOptions) => request<DeviceStatus[]>("/api/devices", options, parseDevices),

  demoStatus: (options?: ApiRequestOptions) => request<DemoStatus>("/api/demo/status", options, parseDemoStatus),

  demoScenarios: (options?: ApiRequestOptions) =>
    request<DemoScenario[]>("/api/demo/scenarios", options, parseDemoScenarios),

  machineVideos: (options?: ApiRequestOptions) =>
    request<MachineVideoEntry[]>("/api/demo/machine-videos", options, parseMachineVideos),

  startDemo: (body: DemoStartRequest, options?: ApiRequestOptions) =>
    request<DemoStatus>("/api/demo/start", { ...options, method: "POST", body: JSON.stringify(body) }, parseDemoStatus),

  stopDemo: (options?: ApiRequestOptions) =>
    request<DemoStatus>("/api/demo/stop", { ...options, method: "POST" }, parseDemoStatus),

  thermalImageFeed: (options?: ApiRequestOptions) =>
    request<ThermalFeedEntry[]>("/api/demo/thermal-image-feed", options, parseThermalFeed),
};

function parseMachineAt(value: unknown, index: number): Machine {
  try {
    return parseMachine(value);
  } catch (error) {
    if (error instanceof ContractError) {
      throw new ContractError(`machines[${index}]${error.path.replace(/^machine/, "")}`, error.expected, error.received);
    }
    throw error;
  }
}
