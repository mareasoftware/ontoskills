import { navClick } from '../helpers';
import { getCategoryColor } from '../uiColors';
import { TrustBadge } from '../components/TrustBadge';
import { InstallBar } from '../components/InstallBar';
import type { Skill, Translations } from '../types';

interface StoreMeta {
  authors: string[];
  categories: string[];
  trustTiers: string[];
}

export function SkillCard({ skill, t, prefix, navigate }: { skill: Skill; t: Translations; prefix: string; navigate: (href: string) => void }) {
  const catColor = skill.category ? getCategoryColor(skill.category) : null;
  return (
    <a
      href={`${prefix}/${skill.qualifiedId}`}
      onClick={navClick(`${prefix}/${skill.qualifiedId}`, navigate)}
      className="skill-card block rounded-xl border border-white/[0.07] bg-white/[0.02] p-5 flex flex-col gap-3 cursor-pointer hover:border-[#52c7e8]/30 hover:bg-[#52c7e8]/[0.04] hover:-translate-y-0.5 hover:shadow-[0_6px_24px_rgba(0,0,0,0.3)] transition-all duration-200"
    >
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-base font-semibold text-[#f5f5f5] leading-tight">{skill.skillId}</h3>
        <TrustBadge tier={skill.trustTier} t={t} />
      </div>
      <code className="text-xs text-[#8a8a8a] font-mono">{skill.qualifiedId}</code>
      <p className="skill-desc text-sm text-[#d4d4d4] leading-relaxed flex-1">{skill.description}</p>
      <div className="flex flex-wrap gap-1.5">
        {skill.category && catColor && <span className={`px-2.5 py-0.5 rounded-full ${catColor.bg} ${catColor.text} text-xs font-medium`}>{skill.category}</span>}
        {skill.aliases.slice(0, 3).map(a => <span key={a} className="px-2 py-0.5 rounded-full bg-white/5 text-xs text-[#8a8a8a]">{a}</span>)}
      </div>
      <InstallBar command={skill.installCommand} t={t} id={`card-${skill.qualifiedId}`} />
    </a>
  );
}

export function StoreView({ loading, filteredSkills, meta, t, prefix, navigate, searchQuery, setSearchQuery, filterAuthor, setFilterAuthor, filterCategory, setFilterCategory, filterTier, setFilterTier, filterSort, setFilterSort, visibleCount, setVisibleCount, lang }: {
  loading: boolean;
  filteredSkills: Skill[];
  meta: StoreMeta;
  t: Translations;
  prefix: string;
  navigate: (href: string) => void;
  searchQuery: string;
  setSearchQuery: (q: string) => void;
  filterAuthor: string;
  setFilterAuthor: (a: string) => void;
  filterCategory: string;
  setFilterCategory: (c: string) => void;
  filterTier: string;
  setFilterTier: (t: string) => void;
  filterSort: string;
  setFilterSort: (s: string) => void;
  visibleCount: number;
  setVisibleCount: (n: number) => void;
  lang: string;
}) {
  const docsLink = lang === 'zh' ? '/zh/docs/getting-started/' : '/docs/getting-started/';
  const visible = filteredSkills.slice(0, visibleCount);
  const remaining = filteredSkills.length - visibleCount;

  return (
    <>
      <div className="mb-10">
        <h2 className="text-2xl sm:text-3xl font-bold text-[#f5f5f5] mb-2">{t.storeLabel}</h2>
        <p className="text-base text-[#d4d4d4]">{t.allSkills}</p>
      </div>

      <div className="mb-8 inline-flex flex-col sm:flex-row sm:items-center gap-4 p-4 rounded-lg bg-white/[0.02] border border-white/[0.06]">
        <span className="text-sm text-[#8a8a8a] shrink-0">{t.getStarted}</span>
        <InstallBar command={t.setupMcpCommand} t={t} id="gs1" />
        <InstallBar command={t.setupSkillCommand} t={t} id="gs2" />
        <a href={docsLink} className="text-sm text-[#52c7e8] hover:underline shrink-0">{t.setupDocs} →</a>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between mb-6">
        <div className="relative flex-1 sm:max-w-md">
          <svg className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-[#8a8a8a]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
          <input className="w-full bg-white/[0.04] border border-white/10 rounded-lg pl-10 pr-4 py-2.5 text-sm text-[#f5f5f5] outline-none placeholder:text-[#8a8a8a] focus:border-[#52c7e8]/50 transition-colors" type="search" placeholder={t.searchPlaceholder} value={searchQuery} onChange={e => setSearchQuery(e.target.value)} aria-label={t.searchPlaceholder} />
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <select value={filterAuthor} onChange={e => setFilterAuthor(e.target.value)} className="bg-white/[0.04] border border-white/10 rounded-lg pl-2.5 pr-7 py-2 text-sm text-[#d4d4d4] outline-none cursor-pointer hover:border-white/20 focus:border-[#52c7e8]/50 transition-colors appearance-none bg-[length:12px] bg-[right_8px_center] bg-no-repeat" style={{ colorScheme: 'dark', backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%238a8a8a' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E\")" }} aria-label={t.author}>
            <option value="">{t.allAuthors}</option>
            {meta.authors.map((a: string) => <option key={a} value={a}>{a}</option>)}
          </select>
          <select value={filterCategory} onChange={e => setFilterCategory(e.target.value)} className="bg-white/[0.04] border border-white/10 rounded-lg pl-2.5 pr-7 py-2 text-sm text-[#d4d4d4] outline-none cursor-pointer hover:border-white/20 focus:border-[#52c7e8]/50 transition-colors appearance-none bg-[length:12px] bg-[right_8px_center] bg-no-repeat" style={{ colorScheme: 'dark', backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%238a8a8a' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E\")" }} aria-label={t.category}>
            <option value="">{t.allCategories}</option>
            {meta.categories.map((c: string) => <option key={c} value={c}>{c}</option>)}
          </select>
          <select value={filterTier} onChange={e => setFilterTier(e.target.value)} className="bg-white/[0.04] border border-white/10 rounded-lg pl-2.5 pr-7 py-2 text-sm text-[#d4d4d4] outline-none cursor-pointer hover:border-white/20 focus:border-[#52c7e8]/50 transition-colors appearance-none bg-[length:12px] bg-[right_8px_center] bg-no-repeat" style={{ colorScheme: 'dark', backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%238a8a8a' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E\")" }} aria-label={t.trustTier}>
            <option value="">{t.allTiers}</option>
            {meta.trustTiers.map((tier: string) => <option key={tier} value={tier}>{tier === 'official' ? t.official : tier === 'verified' ? t.verified : tier === 'community' ? t.community : tier}</option>)}
          </select>
          <select value={filterSort} onChange={e => setFilterSort(e.target.value)} className="bg-white/[0.04] border border-white/10 rounded-lg pl-2.5 pr-7 py-2 text-sm text-[#d4d4d4] outline-none cursor-pointer hover:border-white/20 focus:border-[#52c7e8]/50 transition-colors appearance-none bg-[length:12px] bg-[right_8px_center] bg-no-repeat" style={{ colorScheme: 'dark', backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%238a8a8a' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E\")" }} aria-label={t.sort}>
            <option value="az">{t.sortAZ}</option>
            <option value="za">{t.sortZA}</option>
          </select>
          <span className="text-sm text-[#8a8a8a] ml-2">{filteredSkills.length} {filteredSkills.length === 1 ? t.skill_one : t.skill_other}</span>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20 gap-3">
          <div className="w-5 h-5 border-2 border-[#52c7e8]/30 border-t-[#52c7e8] rounded-full animate-spin"></div>
          <p className="text-[#8a8a8a] text-sm">{t.connecting}</p>
        </div>
      ) : !filteredSkills.length ? (
        <div className="py-16 text-center">
          <p className="text-[#d4d4d4] mb-2">{t.noMatch}</p>
          <p className="text-sm text-[#8a8a8a]">{t.trySearch}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {visible.map((s: Skill) => <SkillCard key={s.qualifiedId} skill={s} t={t} prefix={prefix} navigate={navigate} />)}
        </div>
      )}

      {remaining > 0 && (
        <div className="mt-8 text-center">
          <button onClick={() => setVisibleCount((c: number) => c + 20)} className="px-6 py-2.5 rounded-lg bg-white/[0.04] border border-white/10 text-sm text-[#d4d4d4] hover:bg-white/[0.08] hover:border-white/20 transition-colors">
            {t.loadMore} ({remaining} {t.remaining})
          </button>
        </div>
      )}
    </>
  );
}
