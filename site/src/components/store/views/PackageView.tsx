import { useState, useMemo, useCallback } from 'react';
import type { Skill, GraphNode, Translations } from '../types';
import { navClick, buildGraphData, packageHasDeps } from '../helpers';
import { TrustBadge } from '../components/TrustBadge';
import { InstallBar } from '../components/InstallBar';
import { FileTree } from '../components/FileTree';
import { SkillCard } from './StoreView';
import { KnowledgeGraph3D } from '../graph/KnowledgeGraph3D';

export function PackageView({ loading, skills, packages, pkgId, t, prefix, navigate }: { loading: boolean; skills: Skill[]; packages: any[]; pkgId: string; t: Translations; prefix: string; navigate: (href: string) => void }) {
  const [showPkgGraph, setShowPkgGraph] = useState(false);
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
      <div className="breadcrumb flex items-center gap-2 text-sm mb-8">
        <a href={prefix} onClick={navClick(prefix, navigate)} className="text-[#8a8a8a] hover:text-[#52c7e8] transition-colors">{t.storeLabel}</a>
        <span className="text-[#8a8a8a]">/</span>
        <a href={`${prefix}/${author}`} onClick={navClick(`${prefix}/${author}`, navigate)} className="text-[#8a8a8a] hover:text-[#52c7e8] transition-colors">{author}</a>
        <span className="text-[#8a8a8a]">/</span>
        <span className="text-[#f5f5f5] font-medium">{pkgName}</span>
      </div>
      <div className="mb-8">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 mb-4">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <h2 className="text-2xl sm:text-3xl font-bold text-[#f5f5f5]">{pkgName}</h2>
              <TrustBadge tier={tier} t={t} />
              {ver && <span className="text-sm text-[#8a8a8a]">v{ver}</span>}
            </div>
            <code className="text-sm text-[#8a8a8a] font-mono">{pkgId}</code>
            <div className="flex items-center gap-3 mt-2">
              <span className="text-sm text-[#8a8a8a]">{pkgSkills.length} {t.skills.toLowerCase()}</span>
              <span className="text-[#8a8a8a]">·</span>
              <span className="text-sm text-[#8a8a8a]">{modules.length} {t.files_other}</span>
            </div>
            {rawPkg?.description && <p className="text-sm text-[#d4d4d4] mt-3 leading-relaxed">{rawPkg.description}</p>}
          </div>
          <InstallBar command={`npx ontoskills install ${pkgId}`} t={t} id="pkgInstall" />
        </div>
      </div>
      {/* Knowledge Graph + File Tree side by side */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5 mb-6">
        {hasDeps && graphData && (
          <div className="section-panel">
            <div className="flex items-center justify-between mb-3">
              <div>
                <h3 className="text-base font-semibold text-[#f5f5f5]">{t.knowledgeGraph}</h3>
                <p className="text-xs text-[#8a8a8a] mt-0.5">
                  {graphData.nodes.length} {t.nodes} · {graphData.edges.length} {t.edges}
                </p>
              </div>
            </div>
            <button
              onClick={() => setShowPkgGraph(true)}
              className="w-full flex items-center justify-center gap-2 py-3.5 rounded-lg bg-[#52c7e8]/[0.06] border border-[#52c7e8]/20 hover:bg-[#52c7e8]/[0.12] hover:border-[#52c7e8]/30 transition-all group cursor-pointer"
            >
              <svg className="w-5 h-5 text-[#52c7e8] group-hover:scale-110 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z" /></svg>
              <span className="text-sm font-medium text-[#52c7e8] group-hover:text-[#f5f5f5] transition-colors">{t.openGraph}</span>
            </button>
          </div>
        )}
        <div className="section-panel">
          <h3 className="text-base font-semibold text-[#f5f5f5] mb-3">{t.fileTree} ({modules.length})</h3>
          <div className="max-h-64 overflow-y-auto text-sm">
            <FileTree modules={modules} />
          </div>
        </div>
      </div>

      {/* Fullscreen package graph overlay */}
      {showPkgGraph && graphData && (
        <div className="fixed inset-0 z-50 bg-[#090909] flex flex-col">
          <div className="flex items-center justify-between px-6 py-4 border-b border-white/10">
            <div>
              <h3 className="text-lg font-semibold text-[#f5f5f5]">{t.knowledgeGraph} — {pkgName}</h3>
              <p className="text-xs text-[#8a8a8a] mt-0.5">
                {graphData.nodes.length} {t.nodes} · {graphData.edges.length} {t.edges}
              </p>
            </div>
            <button onClick={() => setShowPkgGraph(false)} className="p-2 rounded-lg hover:bg-white/10 text-[#8a8a8a] hover:text-[#f5f5f5] transition-colors">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          </div>
          <div className="flex-1 relative">
            <KnowledgeGraph3D
              nodes={graphData.nodes}
              edges={graphData.edges}
              onNodeClick={(node) => {
                const skill = skills.find(s => s.packageId === pkgId && s.skillId === node.id);
                if (skill) {
                  setShowPkgGraph(false);
                  navigate(`${prefix}/${skill.qualifiedId}`);
                }
              }}
              height={window.innerHeight - 64}
              t={t}
            />
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
