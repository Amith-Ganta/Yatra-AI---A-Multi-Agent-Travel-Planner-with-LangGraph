import Link from 'next/link';

interface Props {
  destination: string;
  description: string;
  image: string;
}

export default function TripCard({ destination, description, image }: Props) {
  return (
    <Link
      href={`/plan?destination=${encodeURIComponent(destination)}`}
      className="block bg-white rounded-lg shadow-card hover:shadow-hover transition overflow-hidden focus:outline-none focus:ring-2 focus:ring-flipkart-blue"
    >
      <div className="text-6xl h-40 flex items-center justify-center bg-gray-100" aria-hidden="true">
        {image}
      </div>
      <div className="p-4">
        <h3 className="font-bold text-flipkart-dark mb-1">{destination}</h3>
        <p className="text-sm text-gray-600 mb-3">{description}</p>
        <p className="text-flipkart-blue text-sm font-semibold">Plan this trip &rarr;</p>
      </div>
    </Link>
  );
}
