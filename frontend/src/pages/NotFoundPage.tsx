import { Link } from 'react-router-dom';
import { ShieldX } from 'lucide-react';

export function NotFoundPage() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-6 animate-fade-in">
      <ShieldX size={64} className="text-danger-500/60" />
      <div className="text-center">
        <h1 className="text-6xl font-bold text-danger-500/80 font-mono">404</h1>
        <p className="text-surface-400 mt-2">Page not found</p>
      </div>
      <Link to="/status" className="btn-primary">
        Back to Status
      </Link>
    </div>
  );
}
