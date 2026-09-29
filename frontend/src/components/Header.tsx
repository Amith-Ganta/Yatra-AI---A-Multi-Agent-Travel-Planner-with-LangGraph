import Link from 'next/link';

export default function Header() {
  return (
    <header className="bg-flipkart-blue text-white sticky top-0 z-50 shadow-md">
      <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2">
          <span className="text-2xl font-bold">🌍</span>
          <span className="text-xl font-bold">Yatra AI</span>
        </Link>

        <nav className="hidden md:flex gap-8">
          <Link href="/" className="hover:text-blue-200 transition">Home</Link>
          <Link href="/plan" className="hover:text-blue-200 transition">Plan Trip</Link>
          <a href="#" className="hover:text-blue-200 transition">About</a>
          <a href="#" className="hover:text-blue-200 transition">Contact</a>
        </nav>

        <div className="flex items-center gap-4">
          <button className="text-xl">👤</button>
          <button className="md:hidden text-xl">☰</button>
        </div>
      </div>
    </header>
  );
}
