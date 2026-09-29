'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import ProgressBar from '@/components/ProgressBar';
import { useTripPlanner } from '@/hooks/useTripPlanner';
import { TripConstraints } from '@/lib/types';

export default function PlanPage() {
  const router = useRouter();
  const { startPlanning, loading, error, threadId } = useTripPlanner();
  const [step, setStep] = useState(1);

  const [form, setForm] = useState({
    destination: '',
    departure_date: '',
    return_date: '',
    party_size: 2,
    budget: 1000,
  });

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setForm({
      ...form,
      [name]: name === 'party_size' || name === 'budget' ? parseFloat(value) : value,
    });
  };

  const handleNext = () => {
    if (step === 1) {
      if (!form.destination || !form.departure_date || !form.return_date) {
        alert('Please fill all destination and date fields');
        return;
      }
      setStep(2);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.destination || !form.departure_date || !form.return_date || form.party_size < 1) {
      alert('Please fill all fields');
      return;
    }

    const constraints: TripConstraints = form;
    await startPlanning(constraints);

    if (threadId) {
      router.push(`/results/${threadId}`);
    }
  };

  return (
    <div className="max-w-2xl mx-auto px-4 py-12">
      <h1 className="text-3xl font-bold mb-2 text-flipkart-dark">Plan Your Trip</h1>
      <p className="text-gray-600 mb-8">Let AI agents find the perfect itinerary for you</p>

      <ProgressBar current={step} total={2} />

      <form onSubmit={handleSubmit} className="bg-white rounded-lg shadow-card p-8 mt-8">
        {step === 1 && (
          <div className="space-y-6">
            <div>
              <label className="block text-sm font-semibold mb-2 text-flipkart-dark">
                Destination
              </label>
              <input
                type="text"
                name="destination"
                value={form.destination}
                onChange={handleChange}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-flipkart-blue"
                required
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-semibold mb-2 text-flipkart-dark">
                  Departure Date
                </label>
                <input
                  type="date"
                  name="departure_date"
                  value={form.departure_date}
                  onChange={handleChange}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-flipkart-blue"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-semibold mb-2 text-flipkart-dark">
                  Return Date
                </label>
                <input
                  type="date"
                  name="return_date"
                  value={form.return_date}
                  onChange={handleChange}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-flipkart-blue"
                  required
                />
              </div>
            </div>

            <button
              type="button"
              onClick={handleNext}
              className="w-full bg-flipkart-blue hover:bg-blue-600 text-white font-bold py-2 px-4 rounded-lg transition"
            >
              Next
            </button>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-6">
            <div>
              <label className="block text-sm font-semibold mb-2 text-flipkart-dark">
                Number of Travelers
              </label>
              <input
                type="number"
                name="party_size"
                value={form.party_size}
                onChange={handleChange}
                min="1"
                max="10"
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-flipkart-blue"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-semibold mb-2 text-flipkart-dark">
                Total Budget ($)
              </label>
              <input
                type="number"
                name="budget"
                value={form.budget}
                onChange={handleChange}
                min="100"
                step="100"
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-flipkart-blue"
                required
              />
            </div>

            {error && (
              <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
                {error}
              </div>
            )}

            <div className="flex gap-4">
              <button
                type="button"
                onClick={() => setStep(1)}
                className="flex-1 bg-gray-300 hover:bg-gray-400 text-gray-800 font-bold py-2 px-4 rounded-lg transition"
              >
                Back
              </button>
              <button
                type="submit"
                disabled={loading}
                className="flex-1 bg-flipkart-orange hover:bg-orange-600 disabled:bg-gray-400 text-white font-bold py-2 px-4 rounded-lg transition"
              >
                {loading ? 'Planning...' : 'Start Planning'}
              </button>
            </div>
          </div>
        )}
      </form>
    </div>
  );
}
