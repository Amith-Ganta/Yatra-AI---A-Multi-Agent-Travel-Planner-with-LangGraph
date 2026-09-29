interface Props {
  budget: {
    flights: number;
    hotels: number;
    activities: number;
    food: number;
    misc: number;
  };
}

export default function BudgetBreakdown({ budget }: Props) {
  const total = Object.values(budget).reduce((a, b) => a + b, 0);
  const categories = [
    { name: 'Flights', value: budget.flights, color: 'bg-blue-500' },
    { name: 'Hotels', value: budget.hotels, color: 'bg-purple-500' },
    { name: 'Food', value: budget.food, color: 'bg-yellow-500' },
    { name: 'Activities', value: budget.activities, color: 'bg-green-500' },
    { name: 'Misc', value: budget.misc, color: 'bg-gray-500' },
  ];

  return (
    <div>
      <div className="space-y-2">
        {categories.map((cat) => (
          <div key={cat.name}>
            <div className="flex justify-between text-sm mb-1">
              <span className="font-semibold text-gray-700">{cat.name}</span>
              <span className="text-flipkart-orange font-bold">${cat.value}</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div className={`${cat.color} h-2 rounded-full`} style={{ width: `${(cat.value / total) * 100}%` }}></div>
            </div>
          </div>
        ))}
      </div>
      <div className="mt-4 pt-4 border-t">
        <p className="text-xs text-gray-600">Total Budget</p>
        <p className="text-2xl font-bold text-flipkart-orange">${total}</p>
      </div>
    </div>
  );
}
