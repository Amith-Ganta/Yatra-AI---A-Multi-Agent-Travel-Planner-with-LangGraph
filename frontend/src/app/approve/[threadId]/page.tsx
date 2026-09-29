'use client';

import { useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { submitApproval } from '@/lib/api';

export default function ApprovePage() {
  const params = useParams();
  const router = useRouter();
  const threadId = params.threadId as string;

  const [feedback, setFeedback] = useState('');
  const [approved, setApproved] = useState(false);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!approved) {
      alert('Please confirm approval to proceed');
      return;
    }

    setLoading(true);
    try {
      await submitApproval(threadId, feedback, approved);
      setSuccess(true);
      setTimeout(() => router.push('/'), 3000);
    } catch (err) {
      alert('Failed to submit approval');
    } finally {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-12 text-center">
        <h1 className="text-4xl font-bold text-green-600 mb-4">✓ Plan Approved!</h1>
        <p className="text-lg text-gray-600 mb-4">Your trip plan has been saved and approved.</p>
        <p className="text-gray-600">Redirecting to home...</p>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-12">
      <h1 className="text-3xl font-bold mb-2 text-flipkart-dark">Review & Approve</h1>

      <div className="grid grid-cols-2 gap-8 mt-8">
        {/* Left: Itinerary Summary */}
        <div className="bg-white rounded-lg shadow-card p-6">
          <h2 className="text-2xl font-bold mb-4">Trip Summary</h2>
          <div className="space-y-4 text-gray-700">
            <div>
              <p className="font-semibold">Destination</p>
              <p>Paris, France</p>
            </div>
            <div>
              <p className="font-semibold">Dates</p>
              <p>Oct 1-8, 2026 (7 nights)</p>
            </div>
            <div>
              <p className="font-semibold">Travelers</p>
              <p>2 adults</p>
            </div>
            <div>
              <p className="font-semibold">Flights</p>
              <p>Emirates, Oct 1 10:00 AM</p>
            </div>
            <div>
              <p className="font-semibold">Hotel</p>
              <p>Luxury Paris Hotel, 7 nights @ $250/night</p>
            </div>
            <div className="pt-4 border-t-2">
              <p className="text-sm text-gray-600">Estimated Total</p>
              <p className="text-3xl font-bold text-flipkart-orange">$1,700</p>
            </div>
          </div>
        </div>

        {/* Right: Approval Form */}
        <div className="bg-white rounded-lg shadow-card p-6">
          <h2 className="text-2xl font-bold mb-4">Confirmation</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-semibold mb-2 text-flipkart-dark">
                Feedback (Optional)
              </label>
              <textarea
                value={feedback}
                onChange={(e) => setFeedback(e.target.value)}
                placeholder="Any changes or special requests?"
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-flipkart-blue h-24 resize-none"
              />
            </div>

            <div className="flex items-center">
              <input
                type="checkbox"
                id="approve-check"
                checked={approved}
                onChange={(e) => setApproved(e.target.checked)}
                className="w-4 h-4 text-flipkart-blue rounded focus:ring-2 focus:ring-flipkart-blue"
              />
              <label htmlFor="approve-check" className="ml-3 text-sm text-gray-700">
                I approve this travel plan and understand the estimated costs
              </label>
            </div>

            <button
              type="submit"
              disabled={!approved || loading}
              className="w-full bg-flipkart-orange hover:bg-orange-600 disabled:bg-gray-400 text-white font-bold py-3 px-4 rounded-lg transition"
            >
              {loading ? 'Submitting...' : 'Confirm & Book'}
            </button>

            <button
              type="button"
              className="w-full bg-gray-300 hover:bg-gray-400 text-gray-800 font-bold py-2 px-4 rounded-lg transition"
            >
              Request Changes
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
