'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { todayISO } from '@/lib/format';

/** Starts a plan: hands the destination and departure date to the full planning form. */
export default function SearchBar() {
  const router = useRouter();
  const [destination, setDestination] = useState('');
  const [departure, setDeparture] = useState('');
  const [today, setToday] = useState('');

  // Read the date on the client only, so server and browser markup match.
  useEffect(() => setToday(todayISO()), []);

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const params = new URLSearchParams();
    if (destination.trim()) params.set('destination', destination.trim());
    if (departure) params.set('departure', departure);
    const query = params.toString();
    router.push(query ? `/plan?${query}` : '/plan');
  }

  const field =
    'w-full px-4 py-3 border border-gray-300 rounded-lg text-flipkart-dark focus:outline-none focus:ring-2 focus:ring-flipkart-blue';

  return (
    <form onSubmit={handleSubmit} className="bg-white rounded-lg shadow-lg p-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 md:items-end">
        <div>
          <label htmlFor="search-destination" className="block text-sm font-semibold text-gray-700 mb-1">
            Where to?
          </label>
          <input
            id="search-destination"
            type="text"
            value={destination}
            maxLength={100}
            placeholder="City or country"
            onChange={(event) => setDestination(event.target.value)}
            className={field}
          />
        </div>
        <div>
          <label htmlFor="search-departure" className="block text-sm font-semibold text-gray-700 mb-1">
            Departure date
          </label>
          <input
            id="search-departure"
            type="date"
            value={departure}
            min={today || undefined}
            onChange={(event) => setDeparture(event.target.value)}
            className={field}
          />
        </div>
        <button
          type="submit"
          className="w-full bg-flipkart-orange hover:bg-orange-600 text-white font-bold py-3 rounded-lg transition"
        >
          Start planning
        </button>
      </div>
    </form>
  );
}
