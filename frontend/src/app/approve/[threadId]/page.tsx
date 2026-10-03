'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useState } from 'react';
import LoadingSkeleton from '@/components/LoadingSkeleton';
import PlanProgress from '@/components/PlanProgress';
import { usePlanStream } from '@/hooks/usePlanStream';
import { useThread } from '@/hooks/useThread';
import { MAX_FEEDBACK_LENGTH, formatDate, formatMoney } from '@/lib/format';
import type { Plan } from '@/lib/types';

const LINK_PRIMARY =
  'inline-block bg-flipkart-blue hover:bg-blue-600 text-white font-semibold py-2 px-6 rounded-lg transition';
const LINK_SECONDARY =
  'inline-block bg-gray-200 hover:bg-gray-300 text-gray-800 font-semibold py-2 px-6 rounded-lg transition';

function Notice({ title, text, linkHref, linkText }: {
  title: string;
  text: string;
  linkHref: string;
  linkText: string;
}) {
  return (
    <div role="alert" className="bg-white rounded-lg shadow-card p-8 text-center">
      <h1 className="text-2xl font-bold text-flipkart-dark mb-2">{title}</h1>
      <p className="text-gray-600 mb-6">{text}</p>
      <Link href={linkHref} className={LINK_PRIMARY}>
        {linkText}
      </Link>
    </div>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 py-2 border-b last:border-b-0 text-sm">
      <dt className="text-gray-600">{label}</dt>
      <dd className="font-semibold text-flipkart-dark text-right">{value}</dd>
    </div>
  );
}

function PlanSummary({ plan }: { plan: Plan }) {
  const { trip, flights, hotels, budget, itinerary } = plan;
  const travellers = trip?.party_size ?? 1;
  const bestFlight = flights?.best_option ?? null;
  const hotelCount = hotels && hotels.status === 'success' ? hotels.hotels.length : 0;

  return (
    <div className="bg-white rounded-lg shadow-card p-6">
      <h2 className="text-xl font-bold text-flipkart-dark mb-2">
        {trip?.destination ? `Trip to ${trip.destination}` : 'Your trip plan'}
      </h2>
      {plan.summary && <p className="text-sm text-gray-700 mb-4">{plan.summary}</p>}
      <dl>
        {trip && (
          <>
            <SummaryRow
              label="Dates"
              value={`${formatDate(trip.start_date)} to ${formatDate(trip.end_date)} (${trip.days} ${
                trip.days === 1 ? 'day' : 'days'
              })`}
            />
            <SummaryRow label="Travellers" value={`${travellers}`} />
            <SummaryRow label="Your budget" value={formatMoney(trip.budget)} />
          </>
        )}
        {bestFlight && (
          <SummaryRow
            label={flights?.source === 'mock' ? 'Best sample fare' : 'Best flight'}
            value={`${bestFlight.airline}, ${formatMoney(bestFlight.price)} per person`}
          />
        )}
        {hotels && (
          <SummaryRow
            label="Hotel suggestions"
            value={hotelCount > 0 ? `${hotelCount}` : 'None found'}
          />
        )}
        {budget && (
          <SummaryRow
            label="Budget check"
            value={budget.feasibility ? 'Flights fit within your budget' : 'Flights alone exceed your budget'}
          />
        )}
      </dl>

      {itinerary && itinerary.itinerary.length > 0 && (
        <div className="mt-5">
          <h3 className="font-semibold text-flipkart-dark mb-2">Itinerary</h3>
          <ol className="space-y-3">
            {itinerary.itinerary.map((day) => (
              <li key={day.day} className="text-sm">
                <p className="font-semibold text-flipkart-dark">
                  Day {day.day}
                  <span className="font-normal text-gray-600"> · {formatDate(day.date)}</span>
                </p>
                <ul className="list-disc pl-5 text-gray-700">
                  {day.activities.map((activity, index) => (
                    <li key={index}>{activity}</li>
                  ))}
                </ul>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

/** Which draft this is, what changed since the last one, and how many changes are left. */
function RevisionBanner({ plan }: { plan: Plan }) {
  const approval = plan.approval;
  if (!approval || approval.revision === 0) return null;

  const left = Math.max(approval.max_revisions - approval.revision, 0);
  const notApplied = approval.feedback_applied === false;

  return (
    <div
      role="status"
      className={`mb-6 border px-4 py-3 rounded-lg text-sm ${
        notApplied
          ? 'bg-amber-50 border-amber-300 text-amber-900'
          : 'bg-blue-50 border-blue-200 text-blue-900'
      }`}
    >
      <p className="font-semibold">
        Revised draft {approval.revision} of {approval.max_revisions}
      </p>
      {approval.revision_note && <p className="mt-1">{approval.revision_note}</p>}
      <p className="mt-1">
        {left > 0
          ? `You can ask for changes ${left} more ${left === 1 ? 'time' : 'times'}.`
          : 'This is the last draft. If you reject it, we keep it as it is.'}
      </p>
    </div>
  );
}

export default function ApprovePage() {
  const { threadId } = useParams<{ threadId: string }>();
  const { thread, loading, error, reload } = useThread(threadId);
  const { loading: resuming, error: resumeError, nodes, resume } = usePlanStream();

  const [mode, setMode] = useState<'review' | 'changes'>('review');
  const [feedback, setFeedback] = useState('');
  const [actionError, setActionError] = useState<string | null>(null);

  // The answer resumes the paused graph on the server. Whatever the outcome (approved, a revised
  // draft, or a failure), the stored thread is the truth, so the page reloads it afterwards.
  async function answer(approved: boolean, text: string) {
    setActionError(null);
    const run = await resume(threadId, { approved, feedback: text });
    if (run && !approved) {
      setFeedback('');
      setMode('review');
    }
    await reload();
  }

  async function handleApprove() {
    await answer(true, '');
  }

  async function handleRequestChanges(event: React.FormEvent) {
    event.preventDefault();
    const text = feedback.trim();
    if (!text) {
      setActionError('Tell us what you would like to change.');
      return;
    }
    await answer(false, text);
  }

  let body: React.ReactNode;
  if (loading && !thread) {
    body = (
      <div aria-busy="true" aria-label="Loading your trip">
        <LoadingSkeleton />
      </div>
    );
  } else if (error) {
    body = error.notFound ? (
      <Notice title="Trip not found" text={error.message} linkHref="/plan" linkText="Plan a new trip" />
    ) : (
      <div role="alert" className="bg-white rounded-lg shadow-card p-8 text-center">
        <h1 className="text-2xl font-bold text-flipkart-dark mb-2">Something went wrong</h1>
        <p className="text-gray-600 mb-6">{error.message}</p>
        <button type="button" onClick={() => void reload()} className={LINK_PRIMARY}>
          Try again
        </button>
      </div>
    );
  } else if (!thread?.plan) {
    body = (
      <Notice
        title="No plan yet"
        text="This trip does not have a plan to review."
        linkHref="/plan"
        linkText="Plan a trip"
      />
    );
  } else if (thread.plan.status === 'rejected') {
    body = (
      <Notice
        title="There is nothing to approve"
        text={thread.plan.reason}
        linkHref="/plan"
        linkText="Try a different request"
      />
    );
  } else if (thread.plan.status === 'approved') {
    body = (
      <div role="status" className="bg-white rounded-lg shadow-card p-8 text-center">
        <h1 className="text-2xl font-bold text-flipkart-dark mb-2">Plan approved</h1>
        <p className="text-gray-600 mb-6">
          Your approval has been saved. Nothing has been booked: Yatra AI plans trips, it does not
          make reservations.
        </p>
        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Link href={`/results/${threadId}`} className={LINK_PRIMARY}>
            See your plan
          </Link>
          <Link href="/plan" className={LINK_SECONDARY}>
            Plan another trip
          </Link>
        </div>
      </div>
    );
  } else if (thread.plan.status === 'revision_limit') {
    body = (
      <div role="status" className="bg-white rounded-lg shadow-card p-8 text-center">
        <h1 className="text-2xl font-bold text-flipkart-dark mb-2">Revision limit reached</h1>
        <p className="text-gray-600 mb-6">
          We revised this plan {thread.plan.approval?.max_revisions ?? 'the maximum number of'}{' '}
          times. The last draft is kept as it is and has not been approved. You can look at it, or
          start a new request with the changes you want.
        </p>
        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Link href={`/results/${threadId}`} className={LINK_PRIMARY}>
            See the last draft
          </Link>
          <Link href="/plan" className={LINK_SECONDARY}>
            Plan another trip
          </Link>
        </div>
      </div>
    );
  } else {
    const plan = thread.plan;
    body = (
      <>
        <h1 className="text-3xl font-bold text-flipkart-dark mb-2">Review your plan</h1>
        <p className="text-gray-600 mb-6">
          The agents have finished a draft and are waiting for you. Approve it, or reject it with
          what you want changed. Changes are applied to the itinerary; the flights, hotels and
          weather stay as they are.
        </p>

        <RevisionBanner plan={plan} />

        <div className="space-y-6">
          <PlanSummary plan={plan} />

          {resuming ? (
            <PlanProgress nodes={nodes} loading title="Working on your answer" />
          ) : mode === 'review' ? (
            <div className="bg-white rounded-lg shadow-card p-6">
              <p className="text-sm text-gray-600 mb-4">
                Approving saves your decision. Nothing is booked or paid for.
              </p>
              <div className="flex flex-col sm:flex-row gap-3">
                <button
                  type="button"
                  onClick={() => void handleApprove()}
                  disabled={resuming}
                  className="flex-1 bg-flipkart-orange hover:bg-orange-600 disabled:opacity-60 text-white font-bold py-3 px-4 rounded-lg transition"
                >
                  Approve plan
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setActionError(null);
                    setMode('changes');
                  }}
                  disabled={resuming}
                  className="flex-1 bg-gray-200 hover:bg-gray-300 disabled:opacity-60 text-gray-800 font-semibold py-3 px-4 rounded-lg transition"
                >
                  Reject and ask for changes
                </button>
              </div>
              <Link
                href={`/results/${threadId}`}
                className="block mt-4 text-sm text-flipkart-blue hover:underline"
              >
                &larr; Back to the full plan
              </Link>
            </div>
          ) : (
            <form onSubmit={(event) => void handleRequestChanges(event)} className="bg-white rounded-lg shadow-card p-6">
              <label htmlFor="feedback" className="block font-semibold text-flipkart-dark mb-2">
                What should change?
              </label>
              <textarea
                id="feedback"
                value={feedback}
                onChange={(event) => setFeedback(event.target.value)}
                maxLength={MAX_FEEDBACK_LENGTH}
                rows={4}
                disabled={resuming}
                placeholder="For example: more time for museums, and one slow morning."
                className="w-full border border-gray-300 rounded-lg p-3 text-sm focus:outline-none focus:ring-2 focus:ring-flipkart-blue"
              />
              <p className="text-xs text-gray-600 mt-1">
                {feedback.length}/{MAX_FEEDBACK_LENGTH}
              </p>
              <div className="flex flex-col sm:flex-row gap-3 mt-4">
                <button
                  type="submit"
                  disabled={resuming}
                  className="flex-1 bg-flipkart-blue hover:bg-blue-600 disabled:opacity-60 text-white font-semibold py-3 px-4 rounded-lg transition"
                >
                  Send changes
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setActionError(null);
                    setMode('review');
                  }}
                  disabled={resuming}
                  className="flex-1 bg-gray-200 hover:bg-gray-300 disabled:opacity-60 text-gray-800 font-semibold py-3 px-4 rounded-lg transition"
                >
                  Cancel
                </button>
              </div>
            </form>
          )}

          {(actionError || resumeError) && (
            <div role="alert" className="bg-red-50 border border-red-300 text-red-800 px-4 py-3 rounded-lg text-sm">
              {actionError ?? resumeError}
            </div>
          )}
        </div>
      </>
    );
  }

  return <div className="max-w-3xl mx-auto px-4 py-12">{body}</div>;
}
