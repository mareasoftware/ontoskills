import type { Translations } from '../types';
import { getTierColor } from '../uiColors';

export function TrustBadge({ tier, t }: { tier: string; t: Translations }) {
  const { bg, text } = getTierColor(tier);
  const labels: Record<string, string> = {
    official: t.official,
    verified: t.verified,
    community: t.community,
  };
  return <span className={`px-2.5 py-1 rounded-full text-xs font-medium uppercase tracking-wide ${bg} ${text}`}>{labels[tier] || tier}</span>;
}
