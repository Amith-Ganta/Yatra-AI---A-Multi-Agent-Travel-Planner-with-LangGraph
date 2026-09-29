'use client';

import { useState } from 'react';
import { TripConstraints, TripPlan } from '@/lib/types';
import { startTripPlanning, getThread } from '@/lib/api';

interface UseTripPlannerReturn {
  loading: boolean;
  error: string | null;
  threadId: string | null;
  tripPlan: TripPlan | null;
  startPlanning: (constraints: TripConstraints) => Promise<void>;
  fetchPlan: (threadId: string) => Promise<void>;
}

export function useTripPlanner(): UseTripPlannerReturn {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [tripPlan, setTripPlan] = useState<TripPlan | null>(null);

  const startPlanning = async (constraints: TripConstraints) => {
    setLoading(true);
    setError(null);
    try {
      const response = await startTripPlanning(constraints);
      setThreadId(response.thread_id);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to start planning';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const fetchPlan = async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      const thread = await getThread(id);
      setThreadId(id);
      // Note: Full plan structure would be populated by SSE events
      setTripPlan({
        thread_id: id,
        trip_constraints: {
          destination: '',
          departure_date: '',
          return_date: '',
          party_size: 0,
          budget: 0,
        },
        flights: [],
        hotels: [],
        weather: [],
        budget: { flights: 0, hotels: 0, activities: 0, food: 0, misc: 0 },
        itinerary: [],
        total_cost: 0,
        feasibility: true,
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch plan';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return {
    loading,
    error,
    threadId,
    tripPlan,
    startPlanning,
    fetchPlan,
  };
}
