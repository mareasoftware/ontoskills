import { useState, useMemo, useEffect, lazy, Suspense } from 'react';
import type { Skill, PackageManifest, Translations } from '../types';
import { navClick } from '../helpers';
import { buildGraphData, packageHasDeps } from '../graph-builder';
import { OFFICIAL_STORE_REPO_URL } from '../../../data/store';
import { TrustBadge } from '../components/TrustBadge';
import { InstallBar } from '../components/InstallBar';
import { GraphLoader } from '../components/GraphLoader';
import { STAT_COLORS } from '../uiColors';
import { SkillCard } from './StoreView';

const KnowledgeGraph3D = lazy(() => import('../graph/KnowledgeGraph3D').then(m => ({ default: m.KnowledgeGraph3D })));

export function PackageView({ loading, skills, packages, pkgId, t, prefix, navigate }: { loading: boolean; skills: Skill[]; packages: PackageManifest[]; pkgId: string; t: Translations; prefix: string; navigate: (href: string) => void }) {
  const [showPkgGraph, setShowPkgGraph] = useState(false);

  useEffect(() => {
    if (showPkgGraph) {
      document.body.style.overflow = 'hidden';
      return () => { document.body.style.overflow = ''; };
    }
  }, [showPkgGraph]);
  const pkgSkills = skills.filter(s => s.packageId === pkgId);
  const author = pkgId.split('/')[0];
  const pkgName = pkgId.split('/').slice(1).join('/');
  const tier = pkgSkills[0]?.trustTier || 'verified';
  const ver = pkgSkills[0]?.version || '';
  const rawPkg = packages.find(p => p.package_id === pkgId);
  const modules: string[] = rawPkg?.modules || [];
  const hasDeps = packageHasDeps(pkgSkills);
  const graphData = useMemo(() => hasDeps ? buildGraphData(pkgSkills) : null, [pkgSkills, hasDeps]);

  return (
    <>
      <div className="breadcrumb flex flex-wrap items-center gap-1 text-sm mb-8" style={{ rowGap: '2px' }}>
        <a href={prefix} onClick={navClick(prefix, navigate)} className="whitespace-nowrap text-[#8a8a8a] hover:text-[#52c7e8] transition-colors">{t.storeLabel}</a>
        <span className="text-[#8a8a8a]">/</span>
        <a href={`${prefix}/${author}`} onClick={navClick(`${prefix}/${author}`, navigate)} className="whitespace-nowrap text-[#8a8a8a] hover:text-[#52c7e8] transition-colors">{author}</a>
        <span className="text-[#8a8a8a]">/</span>
        <span className="text-[#f5f5f5] font-medium break-all">{pkgName}</span>
      </div>

      {/* Header */}
      <div className="mb-8">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 mb-3">
          <div>
            <h2 className="text-2xl sm:text-3xl font-bold text-[#f5f5f5] mb-2">{pkgName}</h2>
            <div className="flex flex-wrap items-center gap-2 mt-1">
              <TrustBadge tier={tier} t={t} />
              {ver && (
                <span className="px-2 py-0.5 rounded-full bg-white/[0.04] border border-white/[0.08] text-xs text-[#8a8a8a]">v{ver}</span>
              )}
              <code className="text-xs text-[#666] font-mono">{pkgId}</code>
            </div>
          </div>
          <div className="shrink-0">
            <InstallBar command={`npx ontoskills install ${pkgId}`} t={t} id="pkgInstall" />
          </div>
        </div>

        {rawPkg?.description && <p className="text-sm text-[#d4d4d4] mb-4 leading-relaxed">{rawPkg.description}</p>}

        {/* Action row: stats + buttons */}
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          <div className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg ${STAT_COLORS.skills.bg} border ${STAT_COLORS.skills.border}`}>
            <svg className={`w-3.5 h-3.5 ${STAT_COLORS.skills.icon}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
            <span className="text-xs text-[#d4d4d4]">{pkgSkills.length} {pkgSkills.length === 1 ? t.skill_one : t.skill_other}</span>
          </div>
          <div className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg ${STAT_COLORS.modules.bg} border ${STAT_COLORS.modules.border}`}>
            <svg className={`w-3.5 h-3.5 ${STAT_COLORS.modules.icon}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" /></svg>
            <span className="text-xs text-[#d4d4d4]">{modules.length} {modules.length === 1 ? t.file_one : t.file_other}</span>
          </div>

          <span className="text-white/10 mx-0.5">|</span>

          {hasDeps && (
            <button
              onClick={() => setShowPkgGraph(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#52c7e8]/[0.06] border border-[#52c7e8]/20 text-xs font-medium text-[#52c7e8] hover:bg-[#52c7e8]/[0.12] transition-all cursor-pointer"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z" /></svg>
              {t.openGraph}
            </button>
          )}

          <a
            href={`${OFFICIAL_STORE_REPO_URL}/tree/main/packages/${pkgId}`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/[0.03] border border-white/[0.06] text-xs text-[#8a8a8a] hover:text-[#52c7e8] hover:border-[#52c7e8]/20 transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/></svg>
            View on GitHub
          </a>
        </div>
      </div>

      {/* Fullscreen package graph overlay */}
      {showPkgGraph && graphData && (
        <div className="fixed inset-0 z-50 bg-[#090909] flex flex-col overflow-hidden"
          onKeyDown={(e) => { if (e.key === 'Escape') setShowPkgGraph(false); }}
          tabIndex={-1}
          ref={(el) => { if (el && !el.contains(document.activeElement)) el.focus(); }}
        >
          <div className="flex items-center justify-between px-6 py-4 border-b border-white/10">
            <div>
              <h3 className="text-lg font-semibold text-[#f5f5f5]">{t.knowledgeGraph} — {pkgName}</h3>
              <p className="text-xs text-[#8a8a8a] mt-0.5">
                {graphData.nodes.length} {graphData.nodes.length === 1 ? t.node_one : t.node_other} · {graphData.edges.length} {graphData.edges.length === 1 ? t.edge_one : t.edge_other}
              </p>
            </div>
            <button onClick={() => setShowPkgGraph(false)} className="p-2 rounded-lg hover:bg-white/10 text-[#8a8a8a] hover:text-[#f5f5f5] transition-colors" aria-label="Close">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          </div>
          <div className="flex-1 relative">
            <Suspense fallback={<GraphLoader t={t} />}>
              <KnowledgeGraph3D
                nodes={graphData.nodes}
                edges={graphData.edges}
                onNodeClick={(node) => {
                  const skill = skills.find(s => s.packageId === pkgId && s.qualifiedId === node.id);
                  if (skill) {
                    setShowPkgGraph(false);
                    navigate(`${prefix}/${skill.qualifiedId}`);
                  }
                }}
                height="100%"
                t={t}
              />
            </Suspense>
          </div>
        </div>
      )}

      {/* Skills grid — full width, two columns */}
      {loading ? (
        <div className="flex items-center justify-center py-16 gap-3">
          <div className="w-5 h-5 border-2 border-[#52c7e8]/30 border-t-[#52c7e8] rounded-full animate-spin"></div>
          <p className="text-[#8a8a8a] text-sm">{t.connecting}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {pkgSkills.map(s => <SkillCard key={s.qualifiedId} skill={s} t={t} prefix={prefix} navigate={navigate} />)}
        </div>
      )}
    </>
  );
}
