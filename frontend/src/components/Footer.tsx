export default function Footer() {
  return (
    <footer className="bg-flipkart-dark text-white py-8 mt-16">
      <div className="max-w-7xl mx-auto px-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8 mb-8">
          <div>
            <h3 className="font-bold mb-3">About</h3>
            <p className="text-sm text-gray-400">AI-powered travel planning</p>
          </div>
          <div>
            <h3 className="font-bold mb-3">Support</h3>
            <ul className="text-sm text-gray-400 space-y-2">
              <li><a href="#" className="hover:text-white">Help Center</a></li>
              <li><a href="#" className="hover:text-white">Contact Us</a></li>
            </ul>
          </div>
          <div>
            <h3 className="font-bold mb-3">Legal</h3>
            <ul className="text-sm text-gray-400 space-y-2">
              <li><a href="#" className="hover:text-white">Terms</a></li>
              <li><a href="#" className="hover:text-white">Privacy</a></li>
            </ul>
          </div>
          <div>
            <h3 className="font-bold mb-3">Follow</h3>
            <ul className="text-sm text-gray-400 space-y-2">
              <li><a href="#" className="hover:text-white">Twitter</a></li>
              <li><a href="#" className="hover:text-white">GitHub</a></li>
            </ul>
          </div>
        </div>
        <div className="border-t border-gray-700 pt-8 text-center text-sm text-gray-400">
          <p>&copy; 2026 Yatra AI. All rights reserved.</p>
        </div>
      </div>
    </footer>
  );
}
