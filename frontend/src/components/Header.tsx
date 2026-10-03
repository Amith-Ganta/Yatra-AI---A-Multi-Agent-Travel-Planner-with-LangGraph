import Link from 'next/link';

export default function Header() {
  return (
    <header className="bg-flipkart-blue text-white sticky top-0 z-50 shadow-md">
      <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between gap-4">
        <Link href="/" className="flex items-center gap-2">
          <span className="text-2xl" aria-hidden="true">
            🌍
          </span>
          <span className="text-xl font-bold">Yatra AI</span>
        </Link>

        <nav aria-label="Main" className="flex gap-6">
          <Link href="/" className="hover:text-blue-200 transition">
            Home
          </Link>
          <Link href="/plan" className="hover:text-blue-200 transition">
            Plan trip
          </Link>
        </nav>
      </div>
    </header>
  );
}
