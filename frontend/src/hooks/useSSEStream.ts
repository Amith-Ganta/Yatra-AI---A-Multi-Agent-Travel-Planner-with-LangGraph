'use client';

import { useEffect, useState, useCallback } from 'react';
import { SSEEvent } from '@/lib/types';
import { subscribeToStream } from '@/lib/sse';

interface UseSSEStreamReturn {
  events: SSEEvent[];
  loading: boolean;
  error: string | null;
  progress: number;
}

export function useSSEStream(threadId: string | null): UseSSEStreamReturn {
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);

  const handleEvent = useCallback((event: SSEEvent) => {
    setEvents((prev) => [...prev, event]);
    setProgress(event.progress || 0);
  }, []);

  const handleError = useCallback((err: Error) => {
    setError(err.message);
    setLoading(false);
  }, []);

  const handleComplete = useCallback(() => {
    setLoading(false);
  }, []);

  useEffect(() => {
    if (!threadId) return;

    setLoading(true);
    setEvents([]);
    setProgress(0);

    const unsubscribe = subscribeToStream(threadId, {
      onEvent: handleEvent,
      onError: handleError,
      onComplete: handleComplete,
    });

    return () => unsubscribe();
  }, [threadId, handleEvent, handleError, handleComplete]);

  return { events, loading, error, progress };
}
