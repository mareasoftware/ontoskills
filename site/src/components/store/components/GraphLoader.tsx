import { useState, useEffect } from 'react';
import type { Translations } from '../types';

export function GraphLoader({ t }: { t: Translations }) {
  const [progress, setProgress] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setProgress(p => Math.min(p + Math.random() * 15, 90)), 400);
    return () => clearInterval(id);
  }, []);
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4">
      <div className="w-48 h-1.5 rounded-full bg-white/[0.06] overflow-hidden">
        <div className="h-full rounded-full bg-gradient-to-r from-[#52c7e8] to-[#85f496] transition-all duration-500 ease-out" style={{ width: `${progress}%` }} />
      </div>
      <p className="text-[#8a8a8a] text-sm">{t.loading3d}</p>
    </div>
  );
}
