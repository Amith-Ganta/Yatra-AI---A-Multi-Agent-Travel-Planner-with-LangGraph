'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  streamApproval,
  streamPlan,
  type ApprovalDecision,
  type PlanStreamRequest,
} from '@/lib/api';
import type { Plan, PlanStreamEvent } from '@/lib/types';

export interface PlanRun {
  threadId: string;
  plan: Plan;
  /** True when the graph paused on interrupt() and a person has to answer before it goes on. */
  awaitingApproval: boolean;
}

interface UsePlanStream {
  loading: boolean;
  error: string | null;
  /** Agents that have finished, in the order the server reported them. */
  nodes: string[];
  /** Runs a planning request. Resolves to the stored plan, or null if the run failed or was cancelled. */
  start: (request: PlanStreamRequest) => Promise<PlanRun | null>;
  /** Answers a plan that is waiting for approval and resolves to what the graph produced next. */
  resume: (threadId: string, decision: ApprovalDecision) => Promise<PlanRun | null>;
}

const INTERRUPTED = 'The connection closed before the plan was finished. Please try again.';

type Stream = (onEvent: (event: PlanStreamEvent) => void, signal: AbortSignal) => Promise<void>;

export function usePlanStream(): UsePlanStream {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nodes, setNodes] = useState<string[]>([]);
  const controllerRef = useRef<AbortController | null>(null);

  // Leaving the page cancels the run; the server stops it too and stores no plan.
  useEffect(() => () => controllerRef.current?.abort(), []);

  const run = useCallback(async (threadId: string | null, stream: Stream) => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    setLoading(true);
    setError(null);
    setNodes([]);

    const result: {
      threadId: string | null;
      plan: Plan | null;
      awaitingApproval: boolean;
      done: boolean;
      failure: string | null;
    } = { threadId, plan: null, awaitingApproval: false, done: false, failure: null };

    try {
      await stream((event) => {
        switch (event.type) {
          case 'thread':
            result.threadId = event.thread_id;
            break;
          case 'progress':
            setNodes((seen) => (seen.includes(event.node) ? seen : [...seen, event.node]));
            break;
          case 'plan':
            result.plan = event.plan;
            break;
          case 'approval_required':
            result.awaitingApproval = true;
            break;
          case 'done':
            result.done = true;
            break;
          case 'error':
            result.failure = event.error;
            break;
        }
      }, controller.signal);
    } catch (err) {
      if (controller.signal.aborted) return null;
      result.failure = err instanceof Error ? err.message : 'Something went wrong.';
    }

    if (controller.signal.aborted) return null;
    setLoading(false);

    if (result.failure) {
      setError(result.failure);
      return null;
    }
    if (!result.done || !result.threadId || !result.plan) {
      setError(INTERRUPTED);
      return null;
    }
    return {
      threadId: result.threadId,
      plan: result.plan,
      awaitingApproval: result.awaitingApproval,
    };
  }, []);

  const start = useCallback(
    (request: PlanStreamRequest): Promise<PlanRun | null> =>
      run(request.threadId ?? null, (onEvent, signal) => streamPlan(request, onEvent, signal)),
    [run],
  );

  const resume = useCallback(
    (threadId: string, decision: ApprovalDecision): Promise<PlanRun | null> =>
      run(threadId, (onEvent, signal) => streamApproval(threadId, decision, onEvent, signal)),
    [run],
  );

  return { loading, error, nodes, start, resume };
}
