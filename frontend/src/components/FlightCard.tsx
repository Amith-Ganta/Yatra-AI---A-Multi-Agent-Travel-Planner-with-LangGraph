interface Props {
  airline: string;
  departure: string;
  arrival: string;
  price: number;
  duration: string;
}

export default function FlightCard({ airline, departure, arrival, price, duration }: Props) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 flex items-center justify-between shadow-card hover:shadow-hover transition">
      <div className="flex-1">
        <p className="font-semibold text-flipkart-dark">{airline}</p>
        <div className="flex items-center gap-4 mt-2">
          <div>
            <p className="text-lg font-bold text-flipkart-dark">{departure}</p>
            <p className="text-xs text-gray-600">Departure</p>
          </div>
          <div className="text-center flex-1">
            <p className="text-sm text-gray-600">{duration}</p>
            <div className="h-0.5 bg-gray-300 my-1"></div>
          </div>
          <div>
            <p className="text-lg font-bold text-flipkart-dark">{arrival}</p>
            <p className="text-xs text-gray-600">Arrival</p>
          </div>
        </div>
      </div>
      <div className="text-right ml-4">
        <p className="text-2xl font-bold text-flipkart-orange">${price}</p>
        <button className="mt-2 bg-flipkart-blue hover:bg-blue-600 text-white px-4 py-1 rounded text-sm transition">
          Select
        </button>
      </div>
    </div>
  );
}
