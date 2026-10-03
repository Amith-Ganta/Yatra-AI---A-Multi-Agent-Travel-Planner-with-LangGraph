import { formatMoney } from '@/lib/format';
import type { BudgetSection } from '@/lib/types';

const COLOURS: Record<string, string> = {
  flights: 'bg-blue-500',
  hotels: 'bg-purple-500',
  food: 'bg-yellow-500',
  activities: 'bg-green-500',
  misc: 'bg-gray-500',
};

function titleCase(key: string): string {
  const text = key.replace(/_/g, ' ');
  return text.charAt(0).toUpperCase() + text.slice(1);
}

interface Props {
  budget: BudgetSection;
  /** What the traveller said they could spend. */
  tripBudget: number | null;
}

export default function BudgetBreakdown({ budget, tripBudget }: Props) {
  const entries = Object.entries(budget.categories);
  const sum = entries.reduce((acc, [, value]) => acc + value, 0);

  return (
    <div>
      <div className="space-y-3">
        {entries.map(([key, value]) => (
          <div key={key}>
            <div className="flex justify-between text-sm mb-1">
              <span className="font-semibold text-gray-700">{titleCase(key)}</span>
              <span className="text-flipkart-dark font-bold">{formatMoney(value)}</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div
                className={`${COLOURS[key] ?? 'bg-gray-500'} h-2 rounded-full`}
                style={{ width: `${sum > 0 ? Math.min(100, (value / sum) * 100) : 0}%` }}
              />
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4 pt-4 border-t">
        <p className="text-xs text-gray-600">Suggested spend across all categories</p>
        <p className="text-2xl font-bold text-flipkart-orange">{formatMoney(budget.total)}</p>
        <p className="text-xs text-gray-600 mt-1">
          Flights use the best sample fare. The other categories are a standard split of what
          is left, not price quotes.
        </p>
        {tripBudget !== null && (
          <p className="text-xs text-gray-600 mt-1">Your budget: {formatMoney(tripBudget)}</p>
        )}
        <p
          className={`inline-block mt-2 text-xs font-semibold px-2 py-0.5 rounded-full ${
            budget.feasibility ? 'bg-green-100 text-green-800' : 'bg-amber-100 text-amber-900'
          }`}
        >
          {budget.feasibility ? 'Flights fit your budget' : 'Flights exceed your budget'}
        </p>
        {budget.advice && <p className="text-sm text-gray-700 mt-2">{budget.advice}</p>}
      </div>
    </div>
  );
}
