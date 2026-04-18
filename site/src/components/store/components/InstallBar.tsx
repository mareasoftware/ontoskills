import type { Translations } from '../types';
import { CopyButton } from './CopyButton';

export function InstallBar({ command, t, id }: { command: string; t: Translations; id?: string }) {
  return (
    <div className="flex items-center gap-2 px-3 py-2.5 rounded-lg bg-black/30 border border-white/5">
      <code className="text-sm text-[#f5f5f5] font-mono break-all flex-1">{command}</code>
      <CopyButton text={command} t={t} />
    </div>
  );
}
