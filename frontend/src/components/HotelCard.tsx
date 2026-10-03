import type { Hotel } from '@/lib/types';

/** Only http(s) links are rendered; anything else from a search result is ignored. */
function safeUrl(url: string | undefined): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'https:' || parsed.protocol === 'http:' ? parsed.href : null;
  } catch {
    return null;
  }
}

export default function HotelCard({ hotel }: { hotel: Hotel }) {
  const link = safeUrl(hotel.url);

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-card flex flex-col">
      <h3 className="font-bold text-flipkart-dark mb-1">{hotel.name}</h3>
      {hotel.description && (
        <p className="text-gray-600 text-sm mb-3 line-clamp-4">{hotel.description}</p>
      )}
      {link && (
        <a
          href={link}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-auto text-flipkart-blue hover:underline text-sm font-semibold"
        >
          View details
          <span className="sr-only"> for {hotel.name} (opens in a new tab)</span> &rarr;
        </a>
      )}
    </div>
  );
}
