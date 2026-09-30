import { SSEEvent } from './types';

export interface SSEStreamHandler {
  onEvent: (event: SSEEvent) => void;
  onError: (error: Error) => void;
  onComplete: () => void;
}

export function subscribeToStream(
  threadId: string,
  handlers: SSEStreamHandler
): () => void {
  const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
  const eventSource = new EventSource(`${API_BASE}/api/plan/stream?thread_id=${threadId}`);

  eventSource.addEventListener('progress', (event: Event) => {
    try {
      const data = JSON.parse((event as MessageEvent).data);
      handlers.onEvent(data);
    } catch (err) {
      handlers.onError(err as Error);
    }
  });

  eventSource.addEventListener('complete', () => {
    handlers.onComplete();
    eventSource.close();
  });

  eventSource.addEventListener('error', () => {
    handlers.onError(new Error('SSE stream error'));
    eventSource.close();
  });

  return () => {
    eventSource.close();
  };
}
