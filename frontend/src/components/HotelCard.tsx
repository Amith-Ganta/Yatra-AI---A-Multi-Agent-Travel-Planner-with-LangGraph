interface Props {
  name: string;
  description: string;
  url: string;
  price?: number;
  rating?: number;
}

export default function HotelCard({ name, description, url, price, rating }: Props) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg overflow-hidden shadow-card hover:shadow-hover transition">
      <div className="h-40 bg-gradient-to-r from-blue-300 to-blue-200"></div>
      <div className="p-4">
        <h3 className="font-bold text-flipkart-dark text-lg mb-1">{name}</h3>
        {rating && <p className="text-yellow-500 text-sm mb-2">★★★★☆ {rating}</p>}
        <p className="text-gray-600 text-sm mb-3">{description}</p>
        <div className="flex items-center justify-between">
          {price && <p className="text-flipkart-orange font-bold">${price}/night</p>}
          <a href={url} className="text-flipkart-blue hover:underline text-sm font-semibold">
            View Details →
          </a>
        </div>
      </div>
    </div>
  );
}
