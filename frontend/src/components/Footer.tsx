const REPO_URL = 'https://github.com/Amith-Ganta/Yatra-AI---A-Multi-Agent-Travel-Planner-with-LangGraph';

export default function Footer() {
  return (
    <footer className="bg-flipkart-dark text-white py-8 mt-16">
      <div className="max-w-7xl mx-auto px-4">
        <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-6 mb-8">
          <div className="max-w-md">
            <h2 className="font-bold mb-3">Yatra AI</h2>
            <p className="text-sm text-gray-400">
              A multi-agent travel planner built with LangGraph. It drafts a plan for you to review.
              It does not book or sell anything.
            </p>
          </div>
          <div>
            <h2 className="font-bold mb-3">Project</h2>
            <a
              href={REPO_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-gray-400 hover:text-white"
            >
              Source code on GitHub
              <span className="sr-only"> (opens in a new tab)</span>
            </a>
          </div>
        </div>
        <div className="border-t border-gray-700 pt-8 text-center text-sm text-gray-400">
          <p>&copy; 2026 Yatra AI</p>
        </div>
      </div>
    </footer>
  );
}
