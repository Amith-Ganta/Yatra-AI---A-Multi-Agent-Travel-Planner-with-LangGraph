interface Forecast {
  date: string;
  temp_max: number;
  temp_min: number;
  condition: string;
}

interface Props {
  forecast: Forecast[];
}

export default function WeatherPanel({ forecast }: Props) {
  return (
    <div className="grid grid-cols-7 gap-2">
      {forecast.map((day, idx) => (
        <div key={idx} className="bg-white rounded-lg p-3 text-center shadow-card">
          <p className="text-xs font-semibold text-gray-600 mb-2">{day.date.slice(5)}</p>
          <p className="text-2xl mb-2">☀️</p>
          <p className="text-sm font-bold text-flipkart-dark">{day.temp_max}°</p>
          <p className="text-xs text-gray-600">{day.temp_min}°</p>
          <p className="text-xs mt-1">{day.condition}</p>
        </div>
      ))}
    </div>
  );
}
