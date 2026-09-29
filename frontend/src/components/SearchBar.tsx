'use client';

import { useState } from 'react';
import Link from 'next/link';

export default function SearchBar() {
  const [destination, setDestination] = useState('');

  return (
    <div className="bg-white rounded-lg shadow-lg p-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <input
          type="text"
          aria-label="Destination"
          value={destination}
          onChange={(e) => setDestination(e.target.value)}
          className="px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-flipkart-blue"
        />
        <input type="date" className="px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-flipkart-blue" />
        <Link href="/plan">
          <button className="w-full bg-flipkart-orange hover:bg-orange-600 text-white font-bold py-3 rounded-lg transition">
            Search
          </button>
        </Link>
      </div>
    </div>
  );
}
