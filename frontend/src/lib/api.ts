import { parseSseBuffer } from '@/lib/sse';
import type { PlanStreamEvent, ThreadResponse } from '@/lib/types';

// The browser talks to the API directly (CORS is configured on the backend). Next.js rewrites
// are deliberately not used: proxying a long-lived event stream through them buffers it.
export const API_BASE = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(
  /\/+$/,
  '',
);

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function errorFrom(response: Response): Promise<ApiError> {
  let message = `The server answered ${response.status}.`;
  try {
    const body: unknown = await response.json();
    if (body && typeof body === 'object' && 'detail' in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === 'string') message = detail;
    }
  } catch {
    // keep the generic message
  }
  return new ApiError(message, response.status);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, init);
  } catch {
    throw new ApiError('Could not reach the Yatra AI server.', 0);
  }
  if (!response.ok) throw await errorFrom(response);
  return (await response.json()) as T;
}

export function getThread(threadId: string): Promise<ThreadResponse> {
  return request<ThreadResponse>(`/api/threads/${encodeURIComponent(threadId)}`, {
    cache: 'no-store',
  });
}

export interface PlanStreamRequest {
  message: string;
  threadId?: string;
}

export interface ApprovalDecision {
  approved: boolean;
  // required by the server when the plan is rejected
  feedback?: string;
}

/**
 * Send a request that answers with server-sent events and call `onEvent` for each one.
 * Resolves when the stream ends. Rejects with ApiError if the request itself fails
 * (for example 404 for an unknown thread, or 409 when no plan is waiting); a failure inside
 * the run arrives as an `error` event instead.
 */
async function streamEvents(
  path: string,
  init: RequestInit,
  onEvent: (event: PlanStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      signal,
    });
  } catch (err) {
    if (signal?.aborted) throw err;
    throw new ApiError('Could not reach the Yatra AI server.', 0);
  }
  if (!response.ok) throw await errorFrom(response);
  if (!response.body) throw new ApiError('The server sent an empty response.', response.status);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const { payloads, rest } = parseSseBuffer(buffer);
    buffer = rest;
    for (const payload of payloads) onEvent(payload as PlanStreamEvent);
  }
}

/** Start (or continue) a planning run. The run ends with a plan, or pauses for approval. */
export function streamPlan(
  { message, threadId }: PlanStreamRequest,
  onEvent: (event: PlanStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  return streamEvents(
    '/api/plan',
    { method: 'POST', body: JSON.stringify({ message, thread_id: threadId }) },
    onEvent,
    signal,
  );
}

/**
 * Answer a plan that is waiting for approval. This resumes the paused graph, so the response is
 * a stream too: an approval ends with the final plan, a rejection with a revised draft that
 * waits for the next answer.
 */
export function streamApproval(
  threadId: string,
  decision: ApprovalDecision,
  onEvent: (event: PlanStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  return streamEvents(
    `/api/threads/${encodeURIComponent(threadId)}/approve`,
    {
      method: 'PUT',
      body: JSON.stringify({ approved: decision.approved, feedback: decision.feedback ?? '' }),
    },
    onEvent,
    signal,
  );
}
