import Link from 'next/link';

interface Props {
  destination: string;
  description: string;
  price: number;
  image: string;
}

export default function TripCard({ destination, description, price, image }: Props) {
  return (
    <Link href={`/plan?destination=${destination}`}>
      <div className="bg-white rounded-lg shadow-card hover:shadow-hover transition cursor-pointer overflow-hidden">
        <div className="text-6xl h-40 flex items-center justify-center bg-gray-100">
          {image}
        </div>
        <div className="p-4">
          <h3 className="font-bold text-flipkart-dark mb-1">{destination}</h3>
          <p className="text-sm text-gray-600 mb-3">{description}</p>
          <p className="text-flipkart-orange font-bold">From ${price}</p>
        </div>
      </div>
    </Link>
  );
}
