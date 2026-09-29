interface Props {
  destination: string;
  price: number;
}

export default function DealBanner({ destination, price }: Props) {
  return (
    <div className="bg-gradient-to-r from-flipkart-blue to-purple-600 text-white rounded-lg p-6 shadow-card hover:shadow-hover transition">
      <h3 className="text-2xl font-bold mb-2">{destination}</h3>
      <p className="text-lg mb-4">From <span className="text-2xl font-bold">${price}</span></p>
      <button className="bg-flipkart-orange hover:bg-orange-600 text-white font-bold py-2 px-4 rounded transition">
        Explore
      </button>
    </div>
  );
}
