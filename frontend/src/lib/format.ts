import type { PlanRequestForm } from '@/lib/types';

export const MAX_TRAVELLERS = 10;
export const MIN_BUDGET_USD = 100;
export const MAX_NOTES_LENGTH = 500;
export const MAX_FEEDBACK_LENGTH = 1000;

const USD = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
});

export function formatMoney(value: number): string {
  return Number.isFinite(value) ? USD.format(value) : '-';
}

const DATE = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  timeZone: 'UTC',
});

/** "2026-10-08" -> "8 Oct 2026". Anything that is not an ISO date is returned unchanged. */
export function formatDate(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!match) return iso;
  const [, year, month, day] = match;
  return DATE.format(new Date(Date.UTC(Number(year), Number(month) - 1, Number(day))));
}

/** Today in the browser's time zone as YYYY-MM-DD. Call it on the client only. */
export function todayISO(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${month}-${day}`;
}

/** Returns an error message for the first problem found, or null when the form is valid. */
export function validatePlanForm(form: PlanRequestForm, today: string): string | null {
  if (!form.destination.trim()) return 'Enter a destination.';
  if (!form.departureDate || !form.returnDate) return 'Choose both travel dates.';
  if (today && form.departureDate < today) return 'The departure date is in the past.';
  if (form.returnDate < form.departureDate) {
    return 'The return date cannot be before the departure date.';
  }
  if (!Number.isInteger(form.partySize) || form.partySize < 1 || form.partySize > MAX_TRAVELLERS) {
    return `Travellers must be a whole number from 1 to ${MAX_TRAVELLERS}.`;
  }
  if (!Number.isFinite(form.budget) || form.budget < MIN_BUDGET_USD) {
    return `The budget must be at least ${formatMoney(MIN_BUDGET_USD)}.`;
  }
  return null;
}

/** The API takes free text, so the form is written out as one clear request. */
export function buildPlanMessage(form: PlanRequestForm): string {
  const people = form.partySize === 1 ? '1 traveller' : `${form.partySize} travellers`;
  const lines = [
    `Plan a trip to ${form.destination.trim()} for ${people}, leaving on ${form.departureDate} ` +
      `and returning on ${form.returnDate}, with a total budget of ${form.budget} USD.`,
  ];
  const notes = form.notes.trim();
  if (notes) lines.push(`Preferences: ${notes}`);
  return lines.join('\n');
}

const AGENT_LABELS: Record<string, string> = {
  supervisor: 'Understood your request',
  flight: 'Searched flights',
  hotel: 'Found hotels',
  weather: 'Checked the weather',
  budget: 'Worked out the budget',
  itinerary: 'Drafted the itinerary',
  human_approval: 'Recorded your decision',
  revise: 'Applied your changes',
  final_response: 'Put the plan together',
};

export function agentLabel(node: string): string {
  return AGENT_LABELS[node] ?? node.replace(/_/g, ' ');
}

/** Pick an emoji for an Open-Meteo condition string such as "Light rain showers". */
export function weatherIcon(condition: string): string {
  const text = condition.toLowerCase();
  if (text.includes('thunder')) return '⛈️';
  if (text.includes('snow')) return '❄️';
  if (text.includes('rain') || text.includes('drizzle')) return '🌧️';
  if (text.includes('fog')) return '🌫️';
  if (text.includes('overcast')) return '☁️';
  if (text.includes('partly')) return '⛅';
  if (text.includes('clear')) return '☀️';
  return '🌤️';
}
