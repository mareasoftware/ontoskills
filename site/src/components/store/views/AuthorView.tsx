import type { Skill, Translations } from '../types';
import { navClick } from '../helpers';
import { TrustBadge } from '../components/TrustBadge';
import { InstallBar } from '../components/InstallBar';

export function AuthorView({ loading, skills, authorId, t, prefix, navigate }: { loading: boolean; skills: Skill[]; authorId: string; t: Translations; prefix: string; navigate: (href: string) => void }) {
  const authorSkills = skills.filter(s => s.author === authorId);
  const pkgMap: Record<string, Skill[]> = {};
  authorSkills.forEach(s => { pkgMap[s.packageId] = pkgMap[s.packageId] || []; pkgMap[s.packageId].push(s); });
  const allCats = [...new Set(authorSkills.map(s => s.category).filter(Boolean))];
  const tierCounts = authorSkills.reduce<Record<string, number>>((acc, s) => { acc[s.trustTier] = (acc[s.trustTier] || 0) + 1; return acc; }, {});

  return (
    <>
      <div className="breadcrumb flex flex-wrap items-center gap-1 text-sm mb-8" style={{ rowGap: '2px' }}>
        <a href={prefix} onClick={navClick(prefix, navigate)} className="whitespace-nowrap text-[#8a8a8a] hover:text-[#52c7e8] transition-colors">{t.storeLabel}</a>
        <span className="text-[#8a8a8a]">/</span>
        <span className="text-[#f5f5f5] font-medium break-all">{authorId}</span>
      </div>
      <div className="mb-10">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div>
            <h2 className="text-2xl sm:text-3xl font-bold text-[#f5f5f5] mb-2">{authorId}</h2>
            <p className="text-sm text-[#8a8a8a]">{authorSkills.length} {t.totalSkills} · {Object.keys(pkgMap).length} {Object.keys(pkgMap).length === 1 ? t.package_one : t.package_other}</p>
          </div>
          <InstallBar command={`npx ontoskills install ${authorId}/<package>`} t={t} id="authInstall" />
        </div>
        <div className="flex flex-wrap gap-3 mt-4 items-center">
          {allCats.slice(0, 5).map(c => (
            <span key={c} className="px-3 py-1.5 rounded-lg bg-white/[0.03] border border-white/[0.07] text-xs text-[#d4d4d4]">{c}</span>
          ))}
          {allCats.length > 5 && <span className="text-xs text-[#666]">+{allCats.length - 5} {t.more}</span>}
          {Object.entries(tierCounts).map(([tier, count]) => (
            <span key={tier} className="px-3 py-1.5 rounded-lg bg-white/[0.03] border border-white/[0.07] text-xs text-[#8a8a8a]">{tier}: {count}</span>
          ))}
        </div>
      </div>
      {loading ? (
        <div className="flex items-center justify-center py-16 gap-3">
          <div className="w-5 h-5 border-2 border-[#52c7e8]/30 border-t-[#52c7e8] rounded-full animate-spin"></div>
          <p className="text-[#8a8a8a] text-sm">{t.connecting}</p>
        </div>
      ) : Object.entries(pkgMap).map(([pid, pkgSkills]) => {
        const tier = pkgSkills[0]?.trustTier || 'verified';
        const ver = pkgSkills[0]?.version || '';
        const pkgName = pid.split('/').slice(1).join('/');
        const cats = [...new Set(pkgSkills.map(s => s.category).filter(Boolean))];
        return (
          <div
            key={pid}
            className="mb-6 p-5 rounded-xl border border-white/[0.07] bg-white/[0.02] hover:border-white/[0.12] transition-colors cursor-pointer"
            onClick={navClick(`${prefix}/${pid}`, navigate) as unknown as React.MouseEventHandler}
          >
            <div className="flex items-center gap-3 mb-3">
              <span className="text-xl font-semibold text-[#f5f5f5]">{pkgName}</span>
              <TrustBadge tier={tier} t={t} />
              {ver && <span className="text-xs text-[#8a8a8a]">v{ver}</span>}
            </div>
            <div className="flex items-center gap-2 mb-3 flex-wrap">
              <span className="text-xs text-[#8a8a8a] shrink-0">{pkgSkills.length} {pkgSkills.length === 1 ? t.skill_one : t.skill_other}</span>
              <span className="text-[#8a8a8a]">·</span>
              <div className="flex flex-wrap gap-1.5 items-center">
                {cats.slice(0, 3).map(c => <span key={c} className="px-2 py-0.5 rounded-full bg-white/5 text-xs text-[#8a8a8a]">{c}</span>)}
                {cats.length > 3 && <span className="text-xs text-[#666]">+{cats.length - 3} {t.more}</span>}
              </div>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3" onClick={e => e.stopPropagation()}>
              {pkgSkills.slice(0, 5).map(s => (
                <a
                  key={s.qualifiedId}
                  href={`${prefix}/${s.qualifiedId}`}
                  onClick={navClick(`${prefix}/${s.qualifiedId}`, navigate)}
                  className="px-3 py-2 rounded-lg bg-white/[0.02] border border-white/[0.05] text-sm text-[#d4d4d4] hover:border-[#52c7e8]/30 hover:text-[#52c7e8] transition-colors truncate"
                >
                  {s.skillId}
                </a>
              ))}
              {pkgSkills.length > 5 && (
                <a href={`${prefix}/${pid}`} onClick={navClick(`${prefix}/${pid}`, navigate)} className="px-3 py-2 rounded-lg bg-white/[0.02] border border-white/[0.05] text-sm text-[#8a8a8a] hover:text-[#52c7e8] transition-colors">
                  +{pkgSkills.length - 5} {t.more}
                </a>
              )}
            </div>
          </div>
        );
      })}
    </>
  );
}
