// Types mirror the JSON the FastAPI backend returns (see src/agents/plan.py and
// src/api/routes/planning.py). A section is null when its agent did not run.

export interface TripParams {
  destination: string | null;
  start_date: string; // YYYY-MM-DD
  end_date: string; // YYYY-MM-DD
  days: number;
  budget: number;
  party_size: number;
  trip_type: string;
}

export interface Flight {
  airline: string;
  departure: string;
  arrival: string;
  price: number; // per person
  duration: string;
}

export interface FlightsSection {
  flights: Flight[];
  best_option: Flight | null;
  advice: string;
  // "mock" means illustrative fares, not live prices
  source: string | null;
}

export interface Hotel {
  name: string;
  description?: string;
  url?: string;
}

export interface HotelsSection {
  hotels: Hotel[];
  neighborhoods: string[];
  recommendations: string;
  status: string; // "success" | "error"
  error?: string;
}

export interface WeatherDay {
  date: string;
  temp_max: number;
  temp_min: number;
  precipitation_mm?: number;
  condition: string;
}

export interface WeatherSection {
  forecast: WeatherDay[];
  packing_advice: string;
  status: string; // "success" | "error"
  // "forecast" for trips within the forecast horizon, otherwise typical conditions last year
  source?: string | null;
  location?: string | null;
  error?: string;
}

export interface BudgetSection {
  categories: Record<string, number>;
  total: number;
  feasibility: boolean;
  advice: string;
}

export interface ItineraryDay {
  day: number;
  date: string;
  activities: string[];
  weather?: string;
}

export interface ItinerarySection {
  itinerary: ItineraryDay[];
  highlights: string[];
  notes: string;
}

// rejected: the request was refused by the guardrail, so there is nothing to approve.
// awaiting_approval: a draft that the traveller has not answered yet.
// approved: the traveller approved this version.
// revision_limit: the traveller kept asking for changes; the last draft is kept as it is.
export type PlanStatus = 'rejected' | 'awaiting_approval' | 'approved' | 'revision_limit';

export interface PlanApproval {
  // null until the traveller has answered this version of the plan
  approved: boolean | null;
  revision: number;
  max_revisions: number;
  // set on a revised draft: did the model apply the requested changes?
  feedback_applied: boolean | null;
  revision_note: string | null;
}

export interface Plan {
  status: PlanStatus;
  reason: string;
  summary: string | null;
  trip: TripParams | null;
  flights: FlightsSection | null;
  hotels: HotelsSection | null;
  weather: WeatherSection | null;
  budget: BudgetSection | null;
  itinerary: ItinerarySection | null;
  // null for a rejected request
  approval: PlanApproval | null;
}

// What the graph sends when it pauses on interrupt() and waits for a person.
export interface ApprovalRequest {
  kind: 'plan_approval';
  revision: number;
  max_revisions: number;
}

export type PlanStreamEvent =
  | { type: 'thread'; thread_id: string }
  | { type: 'progress'; node: string }
  | { type: 'plan'; plan: Plan }
  | { type: 'approval_required'; request: ApprovalRequest }
  | { type: 'done' }
  | { type: 'error'; error: string };

export interface ThreadMessage {
  message_id: string;
  role: string;
  content: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

// The last decision stored for the thread. It is null while a draft is still waiting.
export interface Approval {
  approved: boolean;
  feedback: string;
}

export interface ThreadResponse {
  thread: {
    thread_id: string;
    user_id: string;
    created_at: string;
    updated_at: string;
    metadata: Record<string, unknown>;
  };
  history: ThreadMessage[];
  message_count: number;
  plan: Plan | null;
  approval: Approval | null;
}

// What the planning form collects. The backend takes free text, so this is turned into a
// sentence by buildPlanMessage().
export interface PlanRequestForm {
  destination: string;
  departureDate: string;
  returnDate: string;
  partySize: number;
  budget: number;
  notes: string;
}
