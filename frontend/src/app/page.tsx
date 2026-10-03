import Link from 'next/link';
import CategoryStrip from '@/components/CategoryStrip';
import SearchBar from '@/components/SearchBar';
import TripCard from '@/components/TripCard';

const featuredDestinations = [
  { destination: 'Paris', description: 'City of Light', image: '🗼' },
  { destination: 'Tokyo', description: 'Modern and traditional', image: '🏯' },
  { destination: 'Barcelona', description: 'Beach and culture', image: '🏖️' },
  { destination: 'Sydney', description: 'Harbour and opera', image: '🌉' },
  { destination: 'Dubai', description: 'Luxury and desert', image: '🏜️' },
  { destination: 'London', description: 'Historic and modern', image: '🎡' },
];

export default function Home() {
  return (
    <div className="bg-flipkart-light">
      <div className="bg-gradient-to-r from-flipkart-blue to-blue-600 py-12">
        <div className="max-w-4xl mx-auto px-4">
          <h1 className="text-4xl font-bold text-white mb-2">Plan your perfect trip</h1>
          <p className="text-blue-100 mb-8">
            Flights, hotels, weather, budget and a day-by-day itinerary from a team of AI agents.
          </p>
          <SearchBar />
        </div>
      </div>

      <CategoryStrip />

      <div className="max-w-7xl mx-auto px-4 py-12">
        <h2 className="text-2xl font-bold mb-8 text-flipkart-dark">Popular destinations</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          {featuredDestinations.map((dest) => (
            <TripCard key={dest.destination} {...dest} />
          ))}
        </div>
      </div>

      <div className="bg-flipkart-blue py-12">
        <div className="max-w-4xl mx-auto px-4 text-center">
          <h2 className="text-3xl font-bold text-white mb-4">Ready to explore?</h2>
          <p className="text-blue-100 mb-8">Tell us where and when, and we will draft the plan.</p>
          <Link
            href="/plan"
            className="inline-block bg-flipkart-orange hover:bg-orange-600 text-white font-bold py-3 px-8 rounded-lg transition"
          >
            Get started
          </Link>
        </div>
      </div>
    </div>
  );
}
