import axios from 'axios';
import { TripConstraints, Thread } from './types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const client = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
});

export async function startTripPlanning(constraints: TripConstraints) {
  const response = await client.post('/api/plan', {
    message: `Plan a trip to ${constraints.destination}`,
    trip_constraints: constraints,
  });
  return response.data;
}

export async function getThread(threadId: string): Promise<Thread> {
  const response = await client.get(`/api/threads/${threadId}`);
  return response.data;
}

export async function submitApproval(threadId: string, feedback: string, approved: boolean) {
  const response = await client.put(`/api/threads/${threadId}/approve`, {
    feedback,
    approved,
  });
  return response.data;
}

export async function checkHealth() {
  try {
    const response = await client.get('/health');
    return response.status === 200;
  } catch {
    return false;
  }
}

export default client;
