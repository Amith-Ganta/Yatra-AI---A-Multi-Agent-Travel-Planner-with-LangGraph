import { formatMoney } from '@/lib/format';
import type { Flight } from '@/lib/types';

interface Props {
  flight: Flight;
  travellers: number;
  highlighted?: boolean;
}

export default function FlightCard({ flight, travellers, highlighted = false }: Props) {
  const total = flight.price * travellers;

  return (
    <div
      className={`bg-white rounded-lg p-4 shadow-card border ${
        highlighted ? 'border-flipkart-blue' : 'border-gray-200'
      }`}
    >
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <p className="font-semibold text-flipkart-dark">{flight.airline}</p>
            {highlighted && (
              <span className="text-xs font-semibold bg-blue-50 text-flipkart-blue px-2 py-0.5 rounded-full">
                Best option
              </span>
            )}
          </div>
          <div className="flex items-center gap-4 mt-2">
            <div>
              <p className="text-lg font-bold text-flipkart-dark">{flight.departure}</p>
              <p className="text-xs text-gray-600">Departure</p>
            </div>
            <div className="text-center flex-1">
              <p className="text-sm text-gray-600">{flight.duration}</p>
              <div className="h-0.5 bg-gray-300 my-1" />
            </div>
            <div>
              <p className="text-lg font-bold text-flipkart-dark">{flight.arrival}</p>
              <p className="text-xs text-gray-600">Arrival</p>
            </div>
          </div>
        </div>
        <div className="sm:text-right">
          <p className="text-2xl font-bold text-flipkart-orange">{formatMoney(flight.price)}</p>
          <p className="text-xs text-gray-600">per person</p>
          {travellers > 1 && (
            <p className="text-xs text-gray-600 mt-1">
              {formatMoney(total)} for {travellers} travellers
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
