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
export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";
export const USE_MOCK = API_BASE.length === 0;

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

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    throw new ApiError(`Request failed: ${path} (${res.status})`, res.status);
  }
  return res.json() as Promise<T>;
}

/** Resolve a value after the mock latency — used by the mock branch of endpoints. */
export function mockResolve<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), MOCK_LATENCY_MS));
}
