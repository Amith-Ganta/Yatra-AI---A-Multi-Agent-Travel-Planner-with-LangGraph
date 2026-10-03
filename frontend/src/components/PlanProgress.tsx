import { agentLabel } from '@/lib/format';

interface Props {
  /** Agents that have finished, in the order the server reported them. */
  nodes: string[];
  /** While true, a spinner row shows that more work is still coming. */
  loading: boolean;
  title?: string;
}

export default function PlanProgress({ nodes, loading, title = 'Planning your trip' }: Props) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="bg-white rounded-lg shadow-card p-6 border border-blue-100"
    >
      <h2 className="font-bold text-flipkart-dark mb-1">{title}</h2>
      <p className="text-sm text-gray-600 mb-4">
        Our agents work in turn. This can take a little while, so please keep this page open.
      </p>
      <ul className="space-y-2">
        {nodes.map((node) => (
          <li key={node} className="flex items-center gap-3 text-sm text-flipkart-dark">
            <span
              aria-hidden="true"
              className="flex h-5 w-5 items-center justify-center rounded-full bg-green-100 text-green-700 text-xs font-bold"
            >
              ✓
            </span>
            {agentLabel(node)}
          </li>
        ))}
        {loading && (
          <li className="flex items-center gap-3 text-sm text-gray-600">
            <span
              aria-hidden="true"
              className="h-5 w-5 rounded-full border-2 border-flipkart-blue border-t-transparent animate-spin"
            />
            Working on the next step...
          </li>
        )}
      </ul>
    </div>
  );
}
