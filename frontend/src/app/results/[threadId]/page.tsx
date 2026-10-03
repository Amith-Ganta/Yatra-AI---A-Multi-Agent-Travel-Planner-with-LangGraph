'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import BudgetBreakdown from '@/components/BudgetBreakdown';
import FlightCard from '@/components/FlightCard';
import HotelCard from '@/components/HotelCard';
import LoadingSkeleton from '@/components/LoadingSkeleton';
import WeatherPanel from '@/components/WeatherPanel';
import { useThread } from '@/hooks/useThread';
import { formatDate, formatMoney } from '@/lib/format';
import type { Approval, Plan } from '@/lib/types';

const PRIMARY_LINK =
  'block text-center w-full bg-flipkart-orange hover:bg-orange-600 text-white font-bold py-3 px-4 rounded-lg transition';
const SECONDARY_LINK =
  'block text-center w-full bg-gray-200 hover:bg-gray-300 text-gray-800 font-semibold py-2 px-4 rounded-lg transition';

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-10">
      <h2 className="text-2xl font-bold mb-4 text-flipkart-dark">{title}</h2>
      {children}
    </section>
  );
}

/** Says where the plan stands: waiting for an answer, approved, or kept as it is at the limit. */
function StatusBanner({ plan, decision }: { plan: Plan; decision: Approval | null }) {
  const approval = plan.approval;

  if (plan.status === 'approved') {
    return (
      <div role="status" className="mb-6 bg-green-50 border border-green-300 text-green-900 px-4 py-3 rounded-lg">
        You approved this plan. Nothing has been booked.
      </div>
    );
  }

  if (plan.status === 'revision_limit') {
    return (
      <div role="status" className="mb-6 bg-amber-50 border border-amber-300 text-amber-900 px-4 py-3 rounded-lg">
        <p className="font-semibold">
          Revision limit reached. This is the last draft and it has not been approved.
        </p>
        {decision?.feedback && (
          <p className="text-sm mt-1">Your last request was: {decision.feedback}</p>
        )}
      </div>
    );
  }

  if (plan.status === 'awaiting_approval') {
    const revised = approval !== null && approval.revision > 0;
    return (
      <div role="status" className="mb-6 bg-blue-50 border border-blue-200 text-blue-900 px-4 py-3 rounded-lg">
        <p className="font-semibold">
          {revised
            ? `Revised draft ${approval.revision} of ${approval.max_revisions}, waiting for your answer.`
            : 'This is a draft, waiting for your answer.'}
        </p>
        {approval?.revision_note && <p className="text-sm mt-1">{approval.revision_note}</p>}
      </div>
    );
  }

  return null;
}

function PlanView({ plan, threadId, decision }: { plan: Plan; threadId: string; decision: Approval | null }) {
  const { trip, flights, hotels, weather, budget, itinerary } = plan;
  const travellers = trip?.party_size ?? 1;

  return (
    <>
      <header className="mb-8">
        <h1 className="text-3xl font-bold text-flipkart-dark">
          {trip?.destination ? `Your trip to ${trip.destination}` : 'Your trip plan'}
        </h1>
        {trip && (
          <p className="text-gray-600 mt-1">
            {formatDate(trip.start_date)} to {formatDate(trip.end_date)}
            {' · '}
            {trip.days} {trip.days === 1 ? 'day' : 'days'}
            {' · '}
            {travellers} {travellers === 1 ? 'traveller' : 'travellers'}
            {' · '}
            budget {formatMoney(trip.budget)}
          </p>
        )}
        {/* The banner below already says "approved" and "revision limit", so repeat neither. */}
        {plan.summary && plan.status !== 'approved' && plan.status !== 'revision_limit' && (
          <p className="text-gray-700 mt-4">{plan.summary}</p>
        )}
      </header>

      <StatusBanner plan={plan} decision={decision} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2">
          {flights && (
            <Section title="Flights">
              {flights.source === 'mock' && (
                <p className="text-sm text-amber-900 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-4">
                  Sample fares: these are illustrative prices, not live availability.
                </p>
              )}
              {flights.flights.length === 0 ? (
                <p className="text-gray-600">No flights were found.</p>
              ) : (
                <div className="space-y-4">
                  {flights.flights.map((flight, index) => (
                    <FlightCard
                      key={`${flight.airline}-${flight.departure}-${index}`}
                      flight={flight}
                      travellers={travellers}
                      highlighted={
                        flights.best_option !== null &&
                        flight.airline === flights.best_option.airline &&
                        flight.departure === flights.best_option.departure &&
                        flight.price === flights.best_option.price
                      }
                    />
                  ))}
                </div>
              )}
              {flights.advice && <p className="text-sm text-gray-700 mt-4">{flights.advice}</p>}
            </Section>
          )}

          {hotels && (
            <Section title="Hotels">
              {hotels.status !== 'success' ? (
                <p className="text-gray-600 bg-white rounded-lg shadow-card p-4">
                  {hotels.error || 'Hotel search was not available for this trip.'}
                </p>
              ) : hotels.hotels.length === 0 ? (
                <p className="text-gray-600">No hotels were found.</p>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {hotels.hotels.map((hotel, index) => (
                    <HotelCard key={`${hotel.name}-${index}`} hotel={hotel} />
                  ))}
                </div>
              )}
              {hotels.neighborhoods.length > 0 && (
                <p className="text-sm text-gray-700 mt-4">
                  <span className="font-semibold">Areas to consider: </span>
                  {hotels.neighborhoods.join(', ')}
                </p>
              )}
              {hotels.recommendations && (
                <p className="text-sm text-gray-700 mt-2">{hotels.recommendations}</p>
              )}
            </Section>
          )}

          {weather && (
            <Section title="Weather">
              <WeatherPanel weather={weather} />
            </Section>
          )}

          {itinerary && (
            <Section title="Itinerary">
              <ol className="space-y-4">
                {itinerary.itinerary.map((day) => (
                  <li key={day.day} className="bg-white rounded-lg shadow-card p-4">
                    <div className="flex flex-wrap items-baseline justify-between gap-2 mb-2">
                      <h3 className="font-bold text-flipkart-dark">
                        Day {day.day}
                        <span className="font-normal text-gray-600"> · {formatDate(day.date)}</span>
                      </h3>
                      {day.weather && <span className="text-xs text-gray-600">{day.weather}</span>}
                    </div>
                    <ul className="list-disc pl-5 space-y-1 text-sm text-gray-700">
                      {day.activities.map((activity, index) => (
                        <li key={index}>{activity}</li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ol>
              {itinerary.highlights.length > 0 && (
                <div className="mt-4">
                  <h3 className="font-semibold text-flipkart-dark mb-1">Highlights</h3>
                  <ul className="list-disc pl-5 space-y-1 text-sm text-gray-700">
                    {itinerary.highlights.map((highlight, index) => (
                      <li key={index}>{highlight}</li>
                    ))}
                  </ul>
                </div>
              )}
              {itinerary.notes && <p className="text-sm text-gray-600 mt-4">{itinerary.notes}</p>}
            </Section>
          )}
        </div>

        <aside className="bg-white rounded-lg shadow-card p-6 h-fit lg:sticky lg:top-24">
          <h2 className="text-xl font-bold mb-4 text-flipkart-dark">Budget</h2>
          {budget ? (
            <BudgetBreakdown budget={budget} tripBudget={trip?.budget ?? null} />
          ) : (
            <p className="text-sm text-gray-600">No budget estimate was made for this trip.</p>
          )}

          <div className="mt-6 space-y-3">
            {plan.status === 'awaiting_approval' && (
              <Link href={`/approve/${threadId}`} className={PRIMARY_LINK}>
                Review and approve
              </Link>
            )}
            <Link href="/plan" className={SECONDARY_LINK}>
              Plan another trip
            </Link>
          </div>
        </aside>
      </div>
    </>
  );
}

export default function ResultsPage() {
  const { threadId } = useParams<{ threadId: string }>();
  const { thread, loading, error, reload } = useThread(threadId);

  let body: React.ReactNode;
  if (loading && !thread) {
    body = (
      <div aria-busy="true" aria-label="Loading your trip">
        <LoadingSkeleton />
      </div>
    );
  } else if (error) {
    body = (
      <div role="alert" className="bg-white rounded-lg shadow-card p-8 text-center">
        <h1 className="text-2xl font-bold text-flipkart-dark mb-2">
          {error.notFound ? 'Trip not found' : 'Something went wrong'}
        </h1>
        <p className="text-gray-600 mb-6">{error.message}</p>
        {error.notFound ? (
          <Link href="/plan" className="inline-block bg-flipkart-blue text-white font-semibold py-2 px-6 rounded-lg">
            Plan a new trip
          </Link>
        ) : (
          <button
            type="button"
            onClick={() => void reload()}
            className="bg-flipkart-blue hover:bg-blue-600 text-white font-semibold py-2 px-6 rounded-lg transition"
          >
            Try again
          </button>
        )}
      </div>
    );
  } else if (!thread?.plan) {
    body = (
      <div className="bg-white rounded-lg shadow-card p-8 text-center">
        <h1 className="text-2xl font-bold text-flipkart-dark mb-2">No plan yet</h1>
        <p className="text-gray-600 mb-6">This trip does not have a finished plan.</p>
        <Link href="/plan" className="inline-block bg-flipkart-blue text-white font-semibold py-2 px-6 rounded-lg">
          Plan a trip
        </Link>
      </div>
    );
  } else if (thread.plan.status === 'rejected') {
    body = (
      <div role="alert" className="bg-amber-50 border border-amber-300 rounded-lg p-8 text-center">
        <h1 className="text-2xl font-bold text-amber-900 mb-2">We could not plan that request</h1>
        <p className="text-amber-900 mb-6">{thread.plan.reason}</p>
        <Link href="/plan" className="inline-block bg-flipkart-blue text-white font-semibold py-2 px-6 rounded-lg">
          Try a different request
        </Link>
      </div>
    );
  } else {
    body = <PlanView plan={thread.plan} threadId={threadId} decision={thread.approval} />;
  }

  return <div className="max-w-7xl mx-auto px-4 py-12">{body}</div>;
}
