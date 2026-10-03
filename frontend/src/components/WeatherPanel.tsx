import { formatDate, weatherIcon } from '@/lib/format';
import type { WeatherSection } from '@/lib/types';

export default function WeatherPanel({ weather }: { weather: WeatherSection }) {
  if (weather.status !== 'success' || weather.forecast.length === 0) {
    return (
      <p className="text-sm text-gray-600 bg-white rounded-lg shadow-card p-4">
        {weather.error || 'Weather data is not available for this trip.'}
      </p>
    );
  }

  const typical = weather.source === 'typical_conditions_last_year';

  return (
    <div>
      <p className="text-sm text-gray-600 mb-3">
        {typical
          ? 'These dates are beyond the forecast range, so this shows the conditions on the same dates last year.'
          : 'Forecast from Open-Meteo.'}
        {weather.location ? ` Location: ${weather.location}.` : ''}
      </p>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-7 gap-2">
        {weather.forecast.map((day) => (
          <div key={day.date} className="bg-white rounded-lg p-3 text-center shadow-card">
            <p className="text-xs font-semibold text-gray-600 mb-2">{formatDate(day.date)}</p>
            <p className="text-2xl mb-2" aria-hidden="true">
              {weatherIcon(day.condition)}
            </p>
            <p className="text-sm font-bold text-flipkart-dark">{Math.round(day.temp_max)}&deg;C</p>
            <p className="text-xs text-gray-600">{Math.round(day.temp_min)}&deg;C</p>
            <p className="text-xs mt-1">{day.condition}</p>
            {typeof day.precipitation_mm === 'number' && day.precipitation_mm > 0 && (
              <p className="text-xs text-flipkart-blue mt-1">{day.precipitation_mm} mm</p>
            )}
          </div>
        ))}
      </div>
      {weather.packing_advice && (
        <p className="mt-3 text-sm text-gray-700 bg-blue-50 rounded-lg p-3">
          <span className="font-semibold">Packing: </span>
          {weather.packing_advice}
        </p>
      )}
    </div>
  );
}
