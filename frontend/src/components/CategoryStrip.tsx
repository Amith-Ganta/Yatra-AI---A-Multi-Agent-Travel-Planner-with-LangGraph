import Link from 'next/link';

export default function CategoryStrip() {
  const categories = [
    { name: 'Flights', icon: '✈️', href: '/plan' },
    { name: 'Hotels', icon: '🏨', href: '/plan' },
    { name: 'Weather', icon: '🌤️', href: '/plan' },
    { name: 'Budget', icon: '💰', href: '/plan' },
    { name: 'Packages', icon: '📦', href: '/plan' },
  ];

  return (
    <div className="bg-white shadow-md">
      <div className="max-w-7xl mx-auto px-4 py-4 overflow-x-auto">
        <div className="flex gap-8 whitespace-nowrap">
          {categories.map((cat) => (
            <Link key={cat.name} href={cat.href}>
              <div className="cursor-pointer text-center hover:scale-110 transition">
                <div className="text-4xl mb-2">{cat.icon}</div>
                <p className="text-sm font-semibold text-flipkart-dark">{cat.name}</p>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
