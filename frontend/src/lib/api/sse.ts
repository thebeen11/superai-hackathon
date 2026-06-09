/**
 * Minimal Server-Sent Events reader for POST endpoints.
 *
 * The backend's `/…/stream` routes emit `text/event-stream` (see backend/app/sse.py):
 * `event: <name>\ndata: <json>\n\n` frames, ending with a terminal `result` (the
 * endpoint's normal JSON payload) and a final `done`. The generated hey-api client
 * can't parse this (it sets parseAs:'stream' and types the body `unknown`), so we read
 * the ReadableStream ourselves.
 */
import { API_BASE, ApiError } from "./client";

/** Mirror of backend `ProgressEvent` (app/events.py). */
export interface ProgressEvent {
  stage: string;
  status: string;
  message: string;
  data: Record<string, unknown>;
  ts?: number;
}

/**
 * POST `body` to an SSE endpoint, invoking `onProgress` for each `progress` frame and
 * resolving with the `result` frame's payload. An `error` frame rejects.
 */
export async function streamSse<TResult>(
  path: string,
  body: unknown,
  onProgress: (evt: ProgressEvent) => void,
): Promise<TResult> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) {
    throw new ApiError(`Stream failed: ${path} (${res.status})`, res.status);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: TResult | undefined;

  // Parse one `event:`/`data:` frame and dispatch it.
  const handleFrame = (frame: string) => {
    let event = "message";
    const dataLines: string[] = [];
    for (const line of frame.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    }
    if (dataLines.length === 0) return;
    const payload = JSON.parse(dataLines.join("\n"));
    if (event === "progress") onProgress(payload as ProgressEvent);
    else if (event === "result") result = payload as TResult;
    else if (event === "error") throw new Error(payload?.message ?? "stream error");
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // Frames are blank-line separated; keep the trailing partial in the buffer.
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      if (frame.trim()) handleFrame(frame);
    }
  }

  if (result === undefined) throw new Error("Stream ended without a result");
  return result;
}
