const ITEMS = [
  { name: 'Flights', icon: '✈️' },
  { name: 'Hotels', icon: '🏨' },
  { name: 'Weather', icon: '🌤️' },
  { name: 'Budget', icon: '💰' },
  { name: 'Itinerary', icon: '🗺️' },
];

/** What one plan covers. Informational only: every plan includes all of these. */
export default function CategoryStrip() {
  return (
    <div className="bg-white shadow-md">
      <div className="max-w-7xl mx-auto px-4 py-4">
        <p className="text-center text-sm text-gray-600 mb-3">Every plan covers</p>
        <ul className="flex flex-wrap justify-center gap-x-8 gap-y-3">
          {ITEMS.map((item) => (
            <li key={item.name} className="text-center">
              <div className="text-3xl mb-1" aria-hidden="true">
                {item.icon}
              </div>
              <p className="text-sm font-semibold text-flipkart-dark">{item.name}</p>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
