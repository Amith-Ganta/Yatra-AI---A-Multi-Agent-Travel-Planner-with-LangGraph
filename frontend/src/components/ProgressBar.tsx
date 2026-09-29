interface Props {
  current: number;
  total: number;
}

export default function ProgressBar({ current, total }: Props) {
  const percentage = (current / total) * 100;

  return (
    <div>
      <div className="flex justify-between items-center mb-2">
        <p className="text-sm font-semibold text-gray-700">Step {current} of {total}</p>
        <p className="text-sm font-semibold text-gray-700">{Math.round(percentage)}%</p>
      </div>
      <div className="w-full bg-gray-200 rounded-full h-3">
        <div className="bg-flipkart-orange h-3 rounded-full transition-all duration-300" style={{ width: `${percentage}%` }}></div>
      </div>
    </div>
  );
}
