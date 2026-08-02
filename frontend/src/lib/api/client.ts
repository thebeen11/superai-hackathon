/**
 * Low-level API client.
 *
 * The base URL comes from NEXT_PUBLIC_API_URL. When it is unset (e.g. local
 * dev before the backend exists) USE_MOCK is true and the endpoint layer in
 * `wtaf.ts` resolves to the in-repo mock data instead of hitting the network.
 *
 * To go live: set NEXT_PUBLIC_API_URL in `.env.local` and implement the
 * matching routes on the backend. No UI code needs to change.
 */
import { client } from "./generated/client.gen";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";
export const USE_MOCK = API_BASE.length === 0;

// Point the generated (hey-api) client at the backend. When USE_MOCK we never
// call it, so leaving the base URL unset is fine.
if (!USE_MOCK) {
  client.setConfig({ baseUrl: API_BASE });
}

/** Simulated latency for the mock layer so loading states are exercised. */
export const MOCK_LATENCY_MS = 350;

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * FastAPI reports a human-readable reason in `detail` ("Already following Bloomberg",
 * "Could not resolve a channel from …"). Those are the messages the UI shows inline, so
 * prefer them over the generic status line; fall back when the body isn't JSON.
 */
async function errorMessage(res: Response, path: string): Promise<string> {
  try {
    const body = await res.json();
    const detail = (body as { detail?: unknown })?.detail;
    if (typeof detail === "string" && detail) return detail;
  } catch {
    // non-JSON error body — fall through to the generic message
  }
  return `Request failed: ${path} (${res.status})`;
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    throw new ApiError(await errorMessage(res, path), res.status);
  }
  return res.json() as Promise<T>;
}

/** Resolve a value after the mock latency — used by the mock branch of endpoints. */
export function mockResolve<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), MOCK_LATENCY_MS));
}
