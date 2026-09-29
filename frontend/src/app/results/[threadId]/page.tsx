'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useSSEStream } from '@/hooks/useSSEStream';
import FlightCard from '@/components/FlightCard';
import HotelCard from '@/components/HotelCard';
import WeatherPanel from '@/components/WeatherPanel';
import BudgetBreakdown from '@/components/BudgetBreakdown';
import LoadingSkeleton from '@/components/LoadingSkeleton';

export default function ResultsPage() {
  const params = useParams();
  const threadId = params.threadId as string;
  const { events, loading, error, progress } = useSSEStream(threadId);

  const mockFlights = [
    { airline: 'Emirates', departure: '10:00 AM', arrival: '6:30 PM', price: 450, duration: '8h 30m' },
    { airline: 'Qatar Airways', departure: '2:15 PM', arrival: '11:45 PM', price: 500, duration: '9h 30m' },
  ];

  const mockHotels = [
    { name: 'Luxury Paris Hotel', description: '5-star luxury in the heart of Paris', url: '#', price: 250, rating: 4.8 },
    { name: 'Budget Hotel Paris', description: 'Comfortable hotel near metro', url: '#', price: 80, rating: 4.2 },
  ];

  const mockWeather = [
    { date: '2026-10-01', temp_max: 22, temp_min: 15, condition: 'Sunny' },
    { date: '2026-10-02', temp_max: 20, temp_min: 14, condition: 'Cloudy' },
  ];

  const mockBudget = {
    flights: 450,
    hotels: 600,
    activities: 200,
    food: 300,
    misc: 150,
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-12">
      <h1 className="text-3xl font-bold mb-2 text-flipkart-dark">Your Trip Plan</h1>
      <p className="text-gray-600 mb-8">Thread ID: {threadId}</p>

      <div className="grid grid-cols-3 gap-8">
        {/* Left: Progress Stream */}
        <div className="col-span-2">
          <div className="bg-white rounded-lg shadow-card p-6 mb-8">
            <h2 className="text-2xl font-bold mb-4">Planning Progress</h2>
            <div className="bg-gray-100 rounded p-4 h-48 overflow-y-auto">
              {events.length === 0 && loading && <LoadingSkeleton />}
              {events.map((event, idx) => (
                <div key={idx} className="mb-3 pb-3 border-b border-gray-300">
                  <div className="flex items-center justify-between">
                    <span className={`font-semibold ${event.status === 'complete' ? 'text-green-600' : 'text-yellow-600'}`}>
                      {event.agent.toUpperCase()}
                    </span>
                    <span className="text-sm text-gray-600">{event.progress}%</span>
                  </div>
                  <p className="text-sm text-gray-700">{event.message}</p>
                </div>
              ))}
              {error && <div className="text-red-600">{error}</div>}
            </div>
          </div>

          {!loading && (
            <>
              {/* Flights */}
              <div className="mb-8">
                <h3 className="text-2xl font-bold mb-4">Flights</h3>
                <div className="space-y-4">
                  {mockFlights.map((flight, idx) => (
                    <FlightCard key={idx} {...flight} />
                  ))}
                </div>
              </div>

              {/* Hotels */}
              <div className="mb-8">
                <h3 className="text-2xl font-bold mb-4">Hotels</h3>
                <div className="space-y-4">
                  {mockHotels.map((hotel, idx) => (
                    <HotelCard key={idx} {...hotel} />
                  ))}
                </div>
              </div>

              {/* Weather */}
              <div>
                <h3 className="text-2xl font-bold mb-4">Weather Forecast</h3>
                <WeatherPanel forecast={mockWeather} />
              </div>
            </>
          )}
        </div>

        {/* Right: Summary Panel */}
        <div className="bg-white rounded-lg shadow-card p-6 h-fit sticky top-20">
          <h2 className="text-2xl font-bold mb-4">Summary</h2>

          <div className="mb-6">
            <h4 className="font-semibold mb-2">Budget Breakdown</h4>
            <BudgetBreakdown budget={mockBudget} />
          </div>

          <div className="mb-6 pb-6 border-b">
            <p className="text-sm text-gray-600">Total Estimated Cost</p>
            <p className="text-3xl font-bold text-flipkart-orange">$1,700</p>
          </div>

          <Link href={`/approve/${threadId}`}>
            <button className="w-full bg-flipkart-orange hover:bg-orange-600 text-white font-bold py-3 px-4 rounded-lg transition">
              Review & Approve
            </button>
          </Link>

          <button className="w-full mt-3 bg-gray-300 hover:bg-gray-400 text-gray-800 font-bold py-2 px-4 rounded-lg transition">
            Request Changes
          </button>
        </div>
      </div>
    </div>
  );
}
