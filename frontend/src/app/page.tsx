'use client';

import Link from 'next/link';
import SearchBar from '@/components/SearchBar';
import CategoryStrip from '@/components/CategoryStrip';
import DealBanner from '@/components/DealBanner';
import TripCard from '@/components/TripCard';

const featuredDestinations = [
  { destination: 'Paris', description: 'City of Light', price: 1200, image: '🗼' },
  { destination: 'Tokyo', description: 'Modern & Traditional', price: 1500, image: '🏯' },
  { destination: 'Barcelona', description: 'Beach & Culture', price: 950, image: '🏖️' },
  { destination: 'Sydney', description: 'Harbor & Opera', price: 1800, image: '🌉' },
  { destination: 'Dubai', description: 'Luxury & Desert', price: 1100, image: '🏜️' },
  { destination: 'London', description: 'Historic & Modern', price: 1050, image: '🎡' },
];

export default function Home() {
  return (
    <div className="bg-flipkart-light">
      {/* Hero Section */}
      <div className="bg-gradient-to-r from-flipkart-blue to-blue-600 py-12">
        <div className="max-w-4xl mx-auto px-4">
          <h1 className="text-4xl font-bold text-white mb-2">Plan Your Perfect Trip</h1>
          <p className="text-blue-100 mb-8">AI-powered travel planning in seconds</p>
          <SearchBar />
        </div>
      </div>

      {/* Category Strip */}
      <CategoryStrip />

      {/* Deal Banners */}
      <div className="max-w-7xl mx-auto px-4 py-8 grid grid-cols-1 md:grid-cols-2 gap-4">
        <DealBanner destination="Paris" price={1200} />
        <DealBanner destination="Tokyo" price={1500} />
      </div>

      {/* Featured Destinations */}
      <div className="max-w-7xl mx-auto px-4 py-12">
        <h2 className="text-2xl font-bold mb-8 text-flipkart-dark">Popular Destinations</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          {featuredDestinations.map((dest) => (
            <TripCard key={dest.destination} {...dest} />
          ))}
        </div>
      </div>

      {/* CTA Section */}
      <div className="bg-flipkart-blue py-12">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-3xl font-bold text-white mb-4">Ready to Explore?</h2>
          <p className="text-blue-100 mb-8">Start planning your next adventure with Yatra AI</p>
          <Link href="/plan">
            <button className="bg-flipkart-orange hover:bg-orange-600 text-white font-bold py-3 px-8 rounded-lg transition">
              Get Started
            </button>
          </Link>
        </div>
      </div>
    </div>
  );
}
