export interface TripConstraints {
  destination: string;
  departure_date: string;
  return_date: string;
  party_size: number;
  budget: number;
}

export interface Flight {
  airline: string;
  departure: string;
  arrival: string;
  price: number;
  duration: string;
}

export interface Hotel {
  name: string;
  description: string;
  url: string;
  price?: number;
  rating?: number;
}

export interface WeatherForecast {
  date: string;
  temp_max: number;
  temp_min: number;
  condition: string;
}

export interface BudgetBreakdown {
  flights: number;
  hotels: number;
  activities: number;
  food: number;
  misc: number;
}

export interface ItineraryDay {
  day: number;
  date: string;
  activities: string[];
}

export interface TripPlan {
  thread_id: string;
  trip_constraints: TripConstraints;
  flights: Flight[];
  hotels: Hotel[];
  weather: WeatherForecast[];
  budget: BudgetBreakdown;
  itinerary: ItineraryDay[];
  total_cost: number;
  feasibility: boolean;
}

export interface SSEEvent {
  agent: string;
  status: 'in_progress' | 'complete' | 'error';
  message: string;
  progress: number;
  timestamp: string;
}

export interface Thread {
  thread_id: string;
  user_id: string;
  status: string;
  metadata: Record<string, any>;
  messages: Array<{
    role: string;
    content: string;
  }>;
  created_at: string;
  updated_at: string;
}
