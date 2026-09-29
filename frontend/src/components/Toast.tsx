interface Props {
  message: string;
  type: 'success' | 'error' | 'info';
  onClose: () => void;
}

export default function Toast({ message, type, onClose }: Props) {
  const bgColor = type === 'success' ? 'bg-green-500' : type === 'error' ? 'bg-red-500' : 'bg-blue-500';

  return (
    <div className={`${bgColor} text-white p-4 rounded-lg shadow-lg flex items-center justify-between animate-slideInUp`}>
      <p>{message}</p>
      <button onClick={onClose} className="ml-4 font-bold">×</button>
    </div>
  );
}
