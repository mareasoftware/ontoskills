/**
 * UI color tokens for OntoStore components.
 *
 * Design rules:
 * - Tier colors convey trust level at a glance
 * - Category colors match graph node colors for visual consistency
 * - Stat pill colors are distinguishable from each other
 * - Accent (cyan #52c7e8) reserved for interactive actions only
 */

// ─── Trust Tiers ────────────────────────────────────────────
export const TIER_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  official:  { bg: 'bg-[#3da0d9]/10',  text: 'text-[#3da0d9]',  border: 'border-[#3da0d9]/20' },
  verified:  { bg: 'bg-[#52bf5a]/10',  text: 'text-[#52bf5a]',  border: 'border-[#52bf5a]/20' },
  community: { bg: 'bg-[#dba32c]/10',  text: 'text-[#dba32c]',  border: 'border-[#dba32c]/20' },
};

export const TIER_DEFAULT = { bg: 'bg-white/5', text: 'text-[#8a8a8a]', border: 'border-white/10' };

// ─── Category colors (matches graph node palette) ──────────
export const CATEGORY_UI_COLORS: Record<string, { bg: string; text: string }> = {
  skill:         { bg: 'bg-[#e0e0e0]/10', text: 'text-[#e0e0e0]' },
  main:          { bg: 'bg-[#dba32c]/10', text: 'text-[#dba32c]' },
  prompt:        { bg: 'bg-[#e07a3a]/10', text: 'text-[#e07a3a]' },
  test:          { bg: 'bg-[#52bf5a]/10', text: 'text-[#52bf5a]' },
  module:        { bg: 'bg-[#c054c9]/10', text: 'text-[#c054c9]' },
  dependency:    { bg: 'bg-[#3da0d9]/10', text: 'text-[#3da0d9]' },
  AntiPattern:   { bg: 'bg-[#e05252]/10', text: 'text-[#e05252]' },
  RecoveryTactic:{ bg: 'bg-[#36c5b8]/10', text: 'text-[#36c5b8]' },
  failure:       { bg: 'bg-[#d84d74]/10', text: 'text-[#d84d74]' },
  yield:         { bg: 'bg-[#38c490]/10', text: 'text-[#38c490]' },
  require:       { bg: 'bg-[#7b6ad8]/10', text: 'text-[#7b6ad8]' },
  tool:          { bg: 'bg-[#e0e0e0]/10', text: 'text-[#e0e0e0]' },
  productivity:  { bg: 'bg-[#5482d6]/10', text: 'text-[#5482d6]' },
  development:   { bg: 'bg-[#a8c034]/10', text: 'text-[#a8c034]' },
};

export const CATEGORY_DEFAULT = { bg: 'bg-[#52c7e8]/10', text: 'text-[#52c7e8]' };

// ─── Stat pill colors ──────────────────────────────────────
export const STAT_COLORS = {
  intents:      { icon: 'text-[#dba32c]', bg: 'bg-[#dba32c]/[0.07]', border: 'border-[#dba32c]/15' },
  dependencies: { icon: 'text-[#e07a3a]', bg: 'bg-[#e07a3a]/[0.07]', border: 'border-[#e07a3a]/15' },
  files:        { icon: 'text-[#7b6ad8]', bg: 'bg-[#7b6ad8]/[0.07]', border: 'border-[#7b6ad8]/15' },
  aliases:      { icon: 'text-[#c054c9]', bg: 'bg-[#c054c9]/[0.07]', border: 'border-[#c054c9]/15' },
  skills:       { icon: 'text-[#52bf5a]', bg: 'bg-[#52bf5a]/[0.07]', border: 'border-[#52bf5a]/15' },
  modules:      { icon: 'text-[#7b6ad8]', bg: 'bg-[#7b6ad8]/[0.07]', border: 'border-[#7b6ad8]/15' },
};

export function getCategoryColor(category: string): { bg: string; text: string } {
  return CATEGORY_UI_COLORS[category] || CATEGORY_DEFAULT;
}

export function getTierColor(tier: string) {
  return TIER_COLORS[tier] || TIER_DEFAULT;
}
