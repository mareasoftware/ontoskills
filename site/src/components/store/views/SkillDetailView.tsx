import { useState, useCallback } from 'react';
import type { Skill, PackageManifest, Translations } from '../types';
import { navClick } from '../helpers';
import { OFFICIAL_STORE_REPO_URL } from '../../../data/store';
import { TrustBadge } from '../components/TrustBadge';
import { InstallBar } from '../components/InstallBar';
import { getCategoryColor, STAT_COLORS } from '../uiColors';
import { FileTree } from './FileTree';
import { GraphButton } from '../components/GraphButton';
import { GraphExplorer } from '../graph/GraphExplorer';

export function SkillDetailView({ skills, packages, pkgId, skillId, t, prefix, navigate }: { skills: Skill[]; packages: PackageManifest[]; pkgId: string; skillId: string; t: Translations; prefix: string; navigate: (href: string) => void }) {
  const skill = skills.find(s => s.packageId === pkgId && s.skillId === skillId);
  const rawPkg = packages.find(p => p.package_id === pkgId);
  const modules: string[] = rawPkg?.modules || [];
  const skillModules = modules.filter(m => m.startsWith(skillId + '/') || m === `${skillId}/ontoskill.ttl`);
  const treeModules = skillModules.length ? skillModules : modules.filter(m => m.startsWith(skillId));

  const [showGraph, setShowGraph] = useState(false);
  const [graphMode, setGraphMode] = useState<'files' | 'knowledge'>('files');

  const openFileKnowledgeMap = useCallback((_: string) => {
    setGraphMode('knowledge');
    setShowGraph(true);
  }, []);

  if (!skill) return <div className="text-center py-20"><p className="text-[#d4d4d4] text-lg">{t.noMatch}</p></div>;

  const author = pkgId.split('/')[0];
  const pkgName = pkgId.split('/').slice(1).join('/');

  return (
    <>
      {showGraph && (
        <GraphExplorer
          skills={skills}
          packages={packages}
          initialStack={[
            { type: 'author', authorId: author },
            { type: 'package', authorId: author, pkgId },
            { type: 'skill', pkgId, skillId, mode: graphMode },
          ]}
          t={t}
          prefix={prefix}
          navigate={navigate}
          onClose={() => setShowGraph(false)}
        />
      )}

      {/* Breadcrumb */}
      <div className="breadcrumb flex flex-wrap items-center gap-1 text-sm mb-8" style={{ rowGap: '2px' }}>
        <a href={prefix} onClick={navClick(prefix, navigate)} className="whitespace-nowrap text-[#8a8a8a] hover:text-[#52c7e8] transition-colors">{t.storeLabel}</a>
        <span className="text-[#8a8a8a]">/</span>
        <a href={`${prefix}/${author}`} onClick={navClick(`${prefix}/${author}`, navigate)} className="whitespace-nowrap text-[#8a8a8a] hover:text-[#52c7e8] transition-colors">{author}</a>
        <span className="text-[#8a8a8a]">/</span>
        <a href={`${prefix}/${pkgId}`} onClick={navClick(`${prefix}/${pkgId}`, navigate)} className="whitespace-nowrap text-[#8a8a8a] hover:text-[#52c7e8] transition-colors">{pkgName}</a>
        <span className="text-[#8a8a8a]">/</span>
        <span className="text-[#f5f5f5] font-medium break-all">{skillId}</span>
      </div>

      {/* Header */}
      <div className="mb-10">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 mb-4">
          <div>
            <h2 className="text-2xl sm:text-3xl font-bold text-[#f5f5f5] tracking-tight mb-2">{skillId}</h2>
            <div className="flex flex-wrap items-center gap-2 mt-1">
              <TrustBadge tier={skill.trustTier} t={t} />
              {skill.version && <span className="px-2 py-0.5 rounded-full bg-white/[0.04] border border-white/[0.08] text-xs text-[#8a8a8a]">v{skill.version}</span>}
              {skill.category && (() => { const cc = getCategoryColor(skill.category); return <span className={`px-2 py-0.5 rounded-full ${cc.bg} border border-white/[0.08] text-xs ${cc.text} font-medium`}>{skill.category}</span>; })()}
            </div>
          </div>
          <div className="shrink-0"><InstallBar command={skill.installCommand} t={t} id="skillInstall" /></div>
        </div>
        {skill.description && <p className="text-base text-[#d4d4d4] leading-relaxed mb-5">{skill.description}</p>}

        {/* Action bar */}
        <div className="flex flex-wrap items-center gap-2 sm:gap-3 mb-2">
          {skill.intents.length > 0 && (
            <div className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg ${STAT_COLORS.intents.bg} border ${STAT_COLORS.intents.border}`}>
              <svg className={`w-3.5 h-3.5 sm:w-4 sm:h-4 ${STAT_COLORS.intents.icon}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
              <span className="text-xs sm:text-sm text-[#d4d4d4]">{skill.intents.length} {skill.intents.length === 1 ? t.intent_one : t.intent_other}</span>
            </div>
          )}
          {skill.dependsOn.length > 0 && (
            <div className="relative group">
              <div className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg ${STAT_COLORS.dependencies.bg} border ${STAT_COLORS.dependencies.border}`}>
                <svg className={`w-3.5 h-3.5 sm:w-4 sm:h-4 ${STAT_COLORS.dependencies.icon}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.172 13.828a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.102 1.101" /></svg>
                <span className="text-xs sm:text-sm text-[#d4d4d4]">{skill.dependsOn.length} {skill.dependsOn.length === 1 ? t.dependency_one : t.dependency_other}</span>
                <svg className="w-3 h-3 text-[#666] shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
              </div>
              <div className="absolute top-full left-0 mt-1 z-50 min-w-[180px] max-w-[320px] rounded-lg bg-[#1a1a1a] border border-white/10 shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-150 py-1.5">
                {skill.dependsOn.map(d => {
                  const dep = skills.find(s => s.packageId === pkgId && s.skillId === d);
                  if (!dep) return (
                    <div key={d} className="flex items-center gap-2 px-3 py-1.5 text-xs text-[#8a8a8a]">
                      <svg className="w-3 h-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.172 13.828a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.102 1.101" /></svg>
                      {d}
                    </div>
                  );
                  return (
                    <a key={d} href={`${prefix}/${dep.qualifiedId}`} onClick={navClick(`${prefix}/${dep.qualifiedId}`, navigate)} className="flex items-center gap-2 px-3 py-1.5 text-xs text-[#d4d4d4] hover:text-[#52c7e8] hover:bg-white/5 transition-colors">
                      <svg className="w-3 h-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.172 13.828a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.102 1.101" /></svg>
                      {d}
                    </a>
                  );
                })}
              </div>
            </div>
          )}
          {treeModules.length > 0 && (
            <div className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg ${STAT_COLORS.files.bg} border ${STAT_COLORS.files.border}`}>
              <svg className={`w-3.5 h-3.5 sm:w-4 sm:h-4 ${STAT_COLORS.files.icon}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" /></svg>
              <span className="text-xs sm:text-sm text-[#d4d4d4]">{treeModules.length} {treeModules.length === 1 ? t.file_one : t.file_other}</span>
            </div>
          )}
          {skill.aliases.length > 0 && (
            <div className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg ${STAT_COLORS.aliases.bg} border ${STAT_COLORS.aliases.border}`}>
              <svg className={`w-3.5 h-3.5 sm:w-4 sm:h-4 ${STAT_COLORS.aliases.icon}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" /></svg>
              <span className="text-xs sm:text-sm text-[#d4d4d4]">{skill.aliases.length} {skill.aliases.length === 1 ? t.alias_one : t.alias_other}</span>
            </div>
          )}
          <GraphButton label={t.exploreGraph} onClick={() => { setGraphMode('files'); setShowGraph(true); }} />
          <a href={`${OFFICIAL_STORE_REPO_URL}/tree/main/packages/${pkgId}/${skillId}`} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/[0.03] border border-white/[0.06] text-xs text-[#8a8a8a] hover:text-[#52c7e8] hover:border-[#52c7e8]/20 transition-colors">
            <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/></svg>
            GitHub
          </a>
        </div>
      </div>

      {/* File tree + Intents */}
      <div className="flex flex-col md:flex-row flex-wrap gap-6 items-start">
        {treeModules.length > 0 && (
          <div className="section-panel w-full md:w-2/5 min-w-0">
            <h3 className="text-sm font-semibold text-[#8a8a8a] uppercase tracking-wider mb-3">{t.fileTree}</h3>
            <div className="space-y-0.5">
              <FileTree paths={treeModules} basePath={skillId} onTtlClick={openFileKnowledgeMap} githubBase={`${OFFICIAL_STORE_REPO_URL}/blob/main/packages/${pkgId}`} />
            </div>
          </div>
        )}
        {skill.intents.length > 0 && (
          <div className="section-panel w-full md:flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-[#8a8a8a] uppercase tracking-wider mb-3">{t.intents}</h3>
            <div className="flex flex-wrap gap-1.5">
              {skill.intents.map(intent => (
                <span key={intent} className="inline-flex items-center gap-1.5 px-2.5 py-1.5 sm:px-3 sm:py-2 rounded-lg bg-[#dba32c]/[0.06] border border-[#dba32c]/20 text-sm text-[#d4d4d4]">
                  <svg className="w-3 h-3 text-[#dba32c] shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                  {intent}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Aliases */}
      {skill.aliases.length > 0 && (
        <div className="section-panel mt-6">
          <h3 className="text-sm font-semibold text-[#8a8a8a] uppercase tracking-wider mb-3">{t.aliases}</h3>
          <div className="flex flex-wrap gap-2">
            {skill.aliases.map(a => <span key={a} className="px-3 py-1.5 rounded-lg bg-white/5 text-sm text-[#8a8a8a] border border-white/[0.06]">{a}</span>)}
          </div>
        </div>
      )}
    </>
  );
}
