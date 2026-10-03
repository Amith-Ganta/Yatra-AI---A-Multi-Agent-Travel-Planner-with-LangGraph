'use client';

import { FormEvent, Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import PlanProgress from '@/components/PlanProgress';
import { usePlanStream } from '@/hooks/usePlanStream';
import {
  MAX_NOTES_LENGTH,
  MAX_TRAVELLERS,
  MIN_BUDGET_USD,
  buildPlanMessage,
  todayISO,
  validatePlanForm,
} from '@/lib/format';
import type { PlanRequestForm } from '@/lib/types';

const FIELD =
  'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-flipkart-blue disabled:bg-gray-100';
const LABEL = 'block text-sm font-semibold mb-2 text-flipkart-dark';

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function PlanForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { loading, error, nodes, start } = usePlanStream();

  const [form, setForm] = useState<PlanRequestForm>(() => {
    const departure = params.get('departure') ?? '';
    return {
      destination: (params.get('destination') ?? '').slice(0, 100),
      departureDate: ISO_DATE.test(departure) ? departure : '',
      returnDate: '',
      partySize: 2,
      budget: 2000,
      notes: '',
    };
  });
  const [formError, setFormError] = useState<string | null>(null);
  const [rejection, setRejection] = useState<string | null>(null);
  // Read on the client only, so the server render and the first client render match.
  const [today, setToday] = useState('');
  useEffect(() => setToday(todayISO()), []);

  const update = <K extends keyof PlanRequestForm>(key: K, value: PlanRequestForm[K]) =>
    setForm((current) => ({ ...current, [key]: value }));

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setRejection(null);

    const problem = validatePlanForm(form, today);
    setFormError(problem);
    if (problem) return;

    const run = await start({ message: buildPlanMessage(form) });
    if (!run) return;
    if (run.plan.status === 'rejected') {
      setRejection(run.plan.reason);
      return;
    }
    // The graph pauses before it finishes: a person has to approve the draft first.
    router.push(run.awaitingApproval ? `/approve/${run.threadId}` : `/results/${run.threadId}`);
  };

  const shownError = formError ?? error;

  return (
    <div className="max-w-2xl mx-auto px-4 py-12">
      <h1 className="text-3xl font-bold mb-2 text-flipkart-dark">Plan your trip</h1>
      <p className="text-gray-600 mb-8">
        Tell us where and when. Our agents will look at flights, hotels and weather, then draft an
        itinerary and a budget. You review the draft and approve it, or ask for changes.
      </p>

      <form onSubmit={handleSubmit} noValidate className="bg-white rounded-lg shadow-card p-6 sm:p-8">
        <fieldset disabled={loading} className="space-y-6">
          <div>
            <label htmlFor="destination" className={LABEL}>
              Destination
            </label>
            <input
              id="destination"
              type="text"
              value={form.destination}
              maxLength={100}
              placeholder="For example Lisbon"
              onChange={(e) => update('destination', e.target.value)}
              className={FIELD}
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label htmlFor="departure" className={LABEL}>
                Departure date
              </label>
              <input
                id="departure"
                type="date"
                value={form.departureDate}
                min={today || undefined}
                onChange={(e) => update('departureDate', e.target.value)}
                className={FIELD}
              />
            </div>
            <div>
              <label htmlFor="return" className={LABEL}>
                Return date
              </label>
              <input
                id="return"
                type="date"
                value={form.returnDate}
                min={form.departureDate || today || undefined}
                onChange={(e) => update('returnDate', e.target.value)}
                className={FIELD}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label htmlFor="travellers" className={LABEL}>
                Travellers
              </label>
              <input
                id="travellers"
                type="number"
                inputMode="numeric"
                min={1}
                max={MAX_TRAVELLERS}
                step={1}
                value={Number.isNaN(form.partySize) ? '' : form.partySize}
                onChange={(e) => update('partySize', e.target.valueAsNumber)}
                className={FIELD}
              />
            </div>
            <div>
              <label htmlFor="budget" className={LABEL}>
                Total budget (USD)
              </label>
              <input
                id="budget"
                type="number"
                inputMode="decimal"
                min={MIN_BUDGET_USD}
                step={50}
                value={Number.isNaN(form.budget) ? '' : form.budget}
                onChange={(e) => update('budget', e.target.valueAsNumber)}
                className={FIELD}
              />
            </div>
          </div>

          <div>
            <label htmlFor="notes" className={LABEL}>
              Preferences <span className="font-normal text-gray-500">(optional)</span>
            </label>
            <textarea
              id="notes"
              rows={3}
              maxLength={MAX_NOTES_LENGTH}
              value={form.notes}
              placeholder="For example: quiet neighbourhood, vegetarian food, museums"
              onChange={(e) => update('notes', e.target.value)}
              className={FIELD}
            />
          </div>

          <button
            type="submit"
            className="w-full bg-flipkart-orange hover:bg-orange-600 disabled:bg-gray-400 text-white font-bold py-3 px-4 rounded-lg transition"
          >
            {loading ? 'Planning...' : 'Plan my trip'}
          </button>
        </fieldset>
      </form>

      {shownError && (
        <div
          role="alert"
          className="mt-6 bg-red-50 border border-red-300 text-red-800 px-4 py-3 rounded-lg"
        >
          {shownError}
        </div>
      )}

      {rejection && (
        <div
          role="alert"
          className="mt-6 bg-amber-50 border border-amber-300 text-amber-900 px-4 py-3 rounded-lg"
        >
          <p className="font-semibold mb-1">We could not plan that request</p>
          <p className="text-sm">{rejection}</p>
        </div>
      )}

      {(loading || nodes.length > 0) && !error && !rejection && (
        <div className="mt-6">
          <PlanProgress nodes={nodes} loading={loading} />
        </div>
      )}
    </div>
  );
}

export default function PlanPage() {
  // useSearchParams needs a Suspense boundary for the static build.
  return (
    <Suspense fallback={<div className="max-w-2xl mx-auto px-4 py-12 text-gray-500">Loading...</div>}>
      <PlanForm />
    </Suspense>
  );
}
