'use client';

import { useCallback, useEffect, useState } from 'react';
import { ApiError, getThread } from '@/lib/api';
import type { ThreadResponse } from '@/lib/types';

interface UseThread {
  thread: ThreadResponse | null;
  loading: boolean;
  /** 404 means the trip does not exist; anything else is a connection or server problem. */
  error: { message: string; notFound: boolean } | null;
  reload: () => Promise<void>;
}

export function useThread(threadId: string): UseThread {
  const [thread, setThread] = useState<ThreadResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<UseThread['error']>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setThread(await getThread(threadId));
    } catch (err) {
      const notFound = err instanceof ApiError && err.status === 404;
      setError({
        notFound,
        message: notFound
          ? 'We could not find that trip.'
          : err instanceof Error
            ? err.message
            : 'Something went wrong.',
      });
    } finally {
      setLoading(false);
    }
  }, [threadId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { thread, loading, error, reload };
}
