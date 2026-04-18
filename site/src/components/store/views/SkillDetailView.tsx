import { useState, useEffect, useCallback, useMemo } from 'react';
import type { Skill, PackageManifest, GraphNode, GraphEdge, Translations } from '../types';
import { navClick, TTL_BASE, buildFileGraphData, parseTtlKnowledgeMap } from '../helpers';
import { OFFICIAL_STORE_REPO_URL } from '../../../data/store';
import { TrustBadge } from '../components/TrustBadge';
import { InstallBar } from '../components/InstallBar';
import { getCategoryColor, STAT_COLORS } from '../uiColors';
import { KnowledgeGraph3D } from '../graph/KnowledgeGraph3D';
import { getNodeColor, getConnectedNodes, CATEGORY_LABELS, CATEGORY_DESCRIPTIONS } from '../graph/colors';
import { clusterGraphData } from '../graph/clustering';

export function SkillDetailView({ skills, packages, pkgId, skillId, t, prefix, navigate }: { skills: Skill[]; packages: PackageManifest[]; pkgId: string; skillId: string; t: Translations; prefix: string; navigate: (href: string) => void }) {
  const skill = skills.find(s => s.packageId === pkgId && s.skillId === skillId);
  const rawPkg = packages.find(p => p.package_id === pkgId);
  const modules: string[] = rawPkg?.modules || [];
  const skillModules = modules.filter(m => m.startsWith(skillId + '/') || m === `${skillId}/ontoskill.ttl`);
  const treeModules = skillModules.length ? skillModules : modules.filter(m => m.startsWith(skillId));

  // Graph state
  const [showGraph, setShowGraph] = useState(false);

  // Lock body scroll when graph overlay is open
  useEffect(() => {
    if (showGraph) {
      document.body.style.overflow = 'hidden';
      return () => { document.body.style.overflow = ''; };
    }
  }, [showGraph]);

  // Reset all graph state when navigating to a different skill
  useEffect(() => {
    setShowGraph(false);
    setGraphMode('files');
    setKnowledgeData(null);
    setLoadingKnowledge(false);
    setGraphError(false);
    setSelectedNode(null);
    setHighlightCategory(null);
    setGraphBreadcrumb([{ label: skillId, fileId: null }]);
  }, [pkgId, skillId]);
  const [graphMode, setGraphMode] = useState<'files' | 'knowledge'>('files');
  const [knowledgeData, setKnowledgeData] = useState<{ nodes: GraphNode[]; edges: GraphEdge[] } | null>(null);
  const [loadingKnowledge, setLoadingKnowledge] = useState(false);
  const [graphError, setGraphError] = useState(false);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [highlightCategory, setHighlightCategory] = useState<string | null>(null);
  const [graphBreadcrumb, setGraphBreadcrumb] = useState<Array<{ label: string; fileId: string | null }>>([
    { label: skillId, fileId: null },
  ]);

  // File graph — built synchronously from module list
  const fileGraphData = useMemo(() => buildFileGraphData(treeModules, skillId), [treeModules, skillId]);

  // Fetch TTL content and parse knowledge map
  const loadKnowledgeGraph = useCallback(async () => {
    if (knowledgeData) return;
    setLoadingKnowledge(true);
    setGraphError(false);
    try {
      const ttlBase = `${TTL_BASE}${pkgId}/`;
      const ttlFiles = treeModules.filter(m => m.endsWith('.ttl'));
      const contents: string[] = [];
      await Promise.all(ttlFiles.map(async (f) => {
        try {
          const res = await fetch(ttlBase + f);
          if (res.ok) contents.push(await res.text());
        } catch { /* skip failed files */ }
      }));
      if (!contents.length) { setGraphError(true); return; }
      setKnowledgeData(parseTtlKnowledgeMap(contents.join('\n'), skillId));
    } catch { setGraphError(true); }
    finally { setLoadingKnowledge(false); }
  }, [pkgId, treeModules, skillId, knowledgeData]);

  const openGraph = useCallback((mode?: 'files' | 'knowledge') => {
    const m = mode || graphMode;
    setShowGraph(true);
    if (m === 'knowledge' && !knowledgeData) {
      loadKnowledgeGraph();
    }
  }, [graphMode, knowledgeData, loadKnowledgeGraph]);

  // Open knowledge map for a single TTL file from the file tree
  const openFileKnowledgeMap = useCallback(async (filePath: string) => {
    if (!filePath.endsWith('.ttl')) return;
    setLoadingKnowledge(true);
    setGraphError(false);
    setSelectedNode(null);
    try {
      const res = await fetch(`${TTL_BASE}${pkgId}/${filePath}`);
      if (!res.ok) throw new Error(`Failed: ${res.status}`);
      const content = await res.text();
      const fileName = filePath.split('/').pop()!.replace('.ttl', '');
      setKnowledgeData(parseTtlKnowledgeMap(content, fileName));
      setGraphMode('knowledge');
      setGraphBreadcrumb([{ label: skillId, fileId: null }, { label: fileName, fileId: filePath }]);
      setShowGraph(true);
    } catch { setGraphError(true); }
    finally { setLoadingKnowledge(false); }
  }, [pkgId, skillId]);

  // Explore a secondary TTL file's knowledge map
  const exploreSecondaryFile = useCallback(async (node: GraphNode) => {
    const fileId = node.qualifiedId;
    if (!fileId.endsWith('.ttl')) return;
    setLoadingKnowledge(true);
    setGraphError(false);
    try {
      const res = await fetch(`${TTL_BASE}${pkgId}/${fileId}`);
      if (!res.ok) throw new Error(`Failed: ${res.status}`);
      const content = await res.text();
      const parsed = parseTtlKnowledgeMap(content, fileId.split('/').pop()!.replace('.ttl', ''));
      setKnowledgeData(parsed);
      setGraphMode('knowledge');
      setGraphBreadcrumb(prev => [...prev, { label: node.label, fileId }]);
      setSelectedNode(null);
    } catch { setGraphError(true); }
    finally { setLoadingKnowledge(false); }
  }, [pkgId]);

  const clusteredKnowledgeData = useMemo(() => {
    if (!knowledgeData) return null;
    return clusterGraphData(knowledgeData.nodes, knowledgeData.edges);
  }, [knowledgeData]);

  const displayGraphData = graphMode === 'files' ? fileGraphData : clusteredKnowledgeData;

  if (!skill) {
    return <div className="text-center py-20"><p className="text-[#d4d4d4] text-lg">{t.noMatch}</p></div>;
  }

  const author = pkgId.split('/')[0];
  const pkgName = pkgId.split('/').slice(1).join('/');

  return (
    <>
      {/* Fullscreen 3D graph overlay */}
      {showGraph && (graphMode === 'files' ? !!fileGraphData : true) && (
        <div
          className="fixed inset-0 z-50 bg-[#090909] flex flex-col overflow-hidden"
          onKeyDown={(e) => { if (e.key === 'Escape') { setShowGraph(false); setSelectedNode(null); } }}
          tabIndex={-1}
          ref={(el) => { if (el && !el.contains(document.activeElement)) el.focus(); }}
        >
          <div className="flex items-center justify-between px-4 sm:px-6 py-3 border-b border-white/10 gap-3">
            <div className="flex flex-wrap items-center gap-2 min-w-0">
              {graphBreadcrumb.map((crumb, i) => (
                <span key={i} className="flex items-center gap-1.5 text-xs shrink-0">
                  {i > 0 && <svg className="w-3 h-3 text-[#8a8a8a]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>}
                  <button
                    onClick={() => {
                      if (i < graphBreadcrumb.length - 1) {
                        setGraphBreadcrumb(prev => prev.slice(0, i + 1));
                        if (i === 0) { setGraphMode('files'); setKnowledgeData(null); }
                      }
                    }}
                    className={`transition-colors truncate max-w-[120px] ${i === graphBreadcrumb.length - 1 ? 'text-[#f5f5f5] font-medium' : 'text-[#8a8a8a] hover:text-[#52c7e8]'}`}
                  >
                    {crumb.label}
                  </button>
                </span>
              ))}
              <div className="flex gap-1 bg-white/5 rounded-lg p-0.5">
                <button onClick={() => setGraphMode('files')} className={`px-2.5 py-1 rounded-md text-xs transition-colors ${graphMode === 'files' ? 'bg-[#52c7e8]/20 text-[#52c7e8]' : 'text-[#8a8a8a] hover:text-[#d4d4d4]'}`}>{t.fileGraph}</button>
                <button onClick={async () => { setGraphMode('knowledge'); if (!knowledgeData) await loadKnowledgeGraph(); }} className={`px-2.5 py-1 rounded-md text-xs transition-colors ${graphMode === 'knowledge' ? 'bg-[#52c7e8]/20 text-[#52c7e8]' : 'text-[#8a8a8a] hover:text-[#d4d4d4]'}`}>{t.knowledgeMap}</button>
              </div>
            </div>
            <button onClick={() => { setShowGraph(false); setSelectedNode(null); }} className="p-2 rounded-lg hover:bg-white/10 text-[#8a8a8a] hover:text-[#f5f5f5] transition-colors shrink-0" aria-label="Close">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          </div>
          <div className="flex-1 relative">
            {loadingKnowledge ? (
              <div className="flex items-center justify-center h-full gap-3">
                <div className="w-5 h-5 border-2 border-[#52c7e8]/30 border-t-[#52c7e8] rounded-full animate-spin" />
                <p className="text-[#8a8a8a] text-sm">{t.loadingGraph}</p>
              </div>
            ) : graphError ? (
              <div className="flex items-center justify-center h-full"><p className="text-[#f9a8d4]">{t.graphError}</p></div>
            ) : (
              <KnowledgeGraph3D
                nodes={displayGraphData.nodes}
                edges={displayGraphData.edges}
                onNodeClick={setSelectedNode}
                onBackgroundClick={() => setSelectedNode(null)}
                highlightCategory={highlightCategory}
                onHighlightCategory={setHighlightCategory}
                height="100%"
                t={t}
                hideLabels={!!selectedNode}
              />
            )}
            {/* Node detail panel */}
            {selectedNode && (
              <div className="absolute sm:right-0 sm:top-0 sm:bottom-0 sm:left-auto sm:w-[360px] bottom-0 left-0 right-0 sm:max-h-none max-h-[60vh] bg-[#0d0d14]/95 backdrop-blur-md sm:border-l border-t border-white/[0.08] overflow-y-auto z-20"
                style={{ animation: 'slideIn 0.25s ease-out' }}
              >
                {/* Header */}
                <div className="px-5 pt-5 pb-4 border-b border-white/[0.07]">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="w-3 h-3 rounded-full" style={{ background: getNodeColor(selectedNode.category, selectedNode.isHighlighted) }} />
                      <span className="text-sm font-semibold text-[#f5f5f5]">
                        {CATEGORY_LABELS[selectedNode.category]?.[0] || selectedNode.category}
                      </span>
                      {selectedNode.isCluster && selectedNode.count && (
                        <span className="text-xs font-bold" style={{ color: getNodeColor(selectedNode.category, false) }}>
                          ×{selectedNode.count}
                        </span>
                      )}
                    </div>
                    <button onClick={() => setSelectedNode(null)} className="p-1.5 rounded-lg hover:bg-white/10 text-[#8a8a8a] transition-colors">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                    </button>
                  </div>
                  {CATEGORY_DESCRIPTIONS[selectedNode.category] && (
                    <p className="text-xs text-[#666] mt-2">{CATEGORY_DESCRIPTIONS[selectedNode.category]}</p>
                  )}
                </div>

                {/* Cluster: list all values */}
                {selectedNode.isCluster && selectedNode.clusterNodes && (
                  <div className="px-5 py-4 border-b border-white/[0.05]">
                    <div className="space-y-2">
                      {selectedNode.clusterNodes.map((cn, i) => (
                        <div
                          key={cn.id || i}
                          className="px-3 py-2.5 rounded-lg bg-white/[0.03] border border-white/[0.06] hover:border-white/[0.12] transition-colors"
                        >
                          <div className="flex items-start gap-2">
                            <span className="w-2 h-2 rounded-full shrink-0 mt-1.5" style={{ background: getNodeColor(cn.category, cn.isHighlighted) }} />
                            <p className="text-sm text-[#d4d4d4] break-words leading-relaxed">{cn.description || cn.value || cn.label}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Single node: value or description */}
                {!selectedNode.isCluster && (selectedNode.description || selectedNode.value) && (
                  <div className="px-5 py-4 border-b border-white/[0.05]">
                    <p className="text-sm text-[#d4d4d4] leading-relaxed break-words">{selectedNode.description || selectedNode.value}</p>
                  </div>
                )}

                {/* Properties */}
                {!selectedNode.isCluster && (
                  <div className="px-5 py-4 border-b border-white/[0.05]">
                    <h3 className="text-xs uppercase tracking-widest text-[#8a8a8a] mb-3">{t.properties}</h3>
                    <div className="space-y-2.5">
                      <div className="flex items-start gap-3">
                        <span className="text-xs text-[#8a8a8a] shrink-0 w-14">{t.type}</span>
                        <div className="flex items-center gap-1.5">
                          <span className="w-2 h-2 rounded-full" style={{ background: getNodeColor(selectedNode.category, selectedNode.isHighlighted) }} />
                          <span className="text-xs text-[#d4d4d4]">{CATEGORY_LABELS[selectedNode.category]?.[0] || selectedNode.category}</span>
                        </div>
                      </div>
                      <div className="flex items-start gap-3">
                        <span className="text-xs text-[#8a8a8a] shrink-0 w-14">{t.id}</span>
                        <code className="text-xs text-[#d4d4d4] font-mono break-all leading-relaxed">{selectedNode.qualifiedId || selectedNode.id}</code>
                      </div>
                      {selectedNode.category === 'dependency' && (() => {
                        const depName = selectedNode.qualifiedId.replace(/^dep:/, '').replace(/_/g, '-');
                        return (
                          <div className="flex items-start gap-3">
                            <span className="text-xs text-[#8a8a8a] shrink-0 w-14">{t.skill_one}</span>
                            <span className="text-xs text-[#d4d4d4]">{depName}</span>
                          </div>
                        );
                      })()}
                      {(['yield', 'require'].includes(selectedNode.category)) && selectedNode.description && (
                        <div className="flex items-start gap-3">
                          <span className="text-xs text-[#8a8a8a] shrink-0 w-14">{t.state}</span>
                          <span className="text-xs text-[#d4d4d4] break-words">{selectedNode.description}</span>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Connected nodes */}
                <div className="px-5 py-4 border-b border-white/[0.05]">
                  <h3 className="text-xs uppercase tracking-widest text-[#8a8a8a] mb-3">{t.connectedTo}</h3>
                  {(() => {
                    const connected = getConnectedNodes(selectedNode, displayGraphData.edges, displayGraphData.nodes);
                    if (!connected.length) return <p className="text-xs text-[#666]">{t.noConnections}</p>;
                    return (
                      <div className="flex flex-wrap gap-2">
                        {connected.map(n => (
                          <button
                            key={n.id}
                            onClick={() => setSelectedNode(n)}
                            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-white/[0.04] border border-white/[0.07] text-xs text-[#d4d4d4] hover:border-[#52c7e8]/30 hover:text-[#52c7e8] transition-colors"
                          >
                            <span className="w-2 h-2 rounded-full shrink-0" style={{ background: getNodeColor(n.category, n.isHighlighted) }} />
                            {n.label}
                            {n.isCluster && n.count && <span className="text-[#8a8a8a]">×{n.count}</span>}
                          </button>
                        ))}
                      </div>
                    );
                  })()}
                </div>

                {/* Actions: explore file / view skill */}
                {!selectedNode.isCluster && (() => {
                  const isTtlFile = ['main', 'prompt', 'test', 'module'].includes(selectedNode.category) && selectedNode.qualifiedId.endsWith('.ttl');
                  const rawId = selectedNode.id.replace(/^dep:/, '').replace(/_/g, '-');
                  const depSkill = skills.find(s => s.packageId === pkgId && s.skillId === rawId);
                  return (
                    <div className="px-5 py-4 space-y-2">
                      {isTtlFile && (
                        <button
                          onClick={() => exploreSecondaryFile(selectedNode)}
                          className="w-full py-2.5 rounded-lg bg-[#52c7e8]/10 text-[#52c7e8] text-sm font-medium hover:bg-[#52c7e8]/20 transition-colors flex items-center justify-center gap-2"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
                          {t.openKnowledgeMap}
                        </button>
                      )}
                      {depSkill && (
                        <button
                          onClick={() => { setShowGraph(false); setSelectedNode(null); navigate(`${prefix}/${depSkill.qualifiedId}`); }}
                          className="w-full py-2.5 rounded-lg bg-white/[0.04] border border-white/[0.07] text-sm text-[#d4d4d4] hover:border-[#52c7e8]/30 hover:text-[#52c7e8] transition-colors"
                        >
                          {t.viewSkill}
                        </button>
                      )}
                    </div>
                  );
                })()}
              </div>
            )}
          </div>
        </div>
      )}

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
      <div className="mb-8">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 mb-3">
          <div>
            <h2 className="text-2xl sm:text-3xl font-bold text-[#f5f5f5] tracking-tight mb-2">{skillId}</h2>
            <div className="flex flex-wrap items-center gap-2 mt-1">
              <TrustBadge tier={skill.trustTier} t={t} />
              {skill.version && (
                <span className="px-2 py-0.5 rounded-full bg-white/[0.04] border border-white/[0.08] text-xs text-[#8a8a8a]">v{skill.version}</span>
              )}
              {skill.category && (() => {
                const cc = getCategoryColor(skill.category);
                return <span className={`px-2 py-0.5 rounded-full ${cc.bg} border border-white/[0.08] text-xs ${cc.text} font-medium`}>{skill.category}</span>;
              })()}
              <code className="text-xs text-[#666] font-mono">{skill.qualifiedId}</code>
            </div>
          </div>
          <div className="shrink-0">
            <InstallBar command={skill.installCommand} t={t} id="skillInstall" />
          </div>
        </div>

        {skill.description && <p className="text-base text-[#d4d4d4] leading-relaxed mb-4">{skill.description}</p>}

        {/* Action bar: stats pills + graph buttons + GitHub */}
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          {skill.intents.length > 0 && (
            <div className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg ${STAT_COLORS.intents.bg} border ${STAT_COLORS.intents.border}`}>
              <svg className={`w-3.5 h-3.5 ${STAT_COLORS.intents.icon}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
              <span className="text-xs text-[#d4d4d4]">{skill.intents.length} {t.intents.toLowerCase()}</span>
            </div>
          )}
          {skill.dependsOn.length > 0 && (
            <div className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg ${STAT_COLORS.dependencies.bg} border ${STAT_COLORS.dependencies.border}`}>
              <svg className={`w-3.5 h-3.5 ${STAT_COLORS.dependencies.icon}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.172 13.828a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.102 1.101" /></svg>
              <span className="text-xs text-[#d4d4d4]">{skill.dependsOn.length} {t.dependencies.toLowerCase()}</span>
            </div>
          )}
          {treeModules.length > 0 && (
            <div className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg ${STAT_COLORS.files.bg} border ${STAT_COLORS.files.border}`}>
              <svg className={`w-3.5 h-3.5 ${STAT_COLORS.files.icon}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" /></svg>
              <span className="text-xs text-[#d4d4d4]">{treeModules.length} {t.files_other}</span>
            </div>
          )}
          {skill.aliases.length > 0 && (
            <div className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg ${STAT_COLORS.aliases.bg} border ${STAT_COLORS.aliases.border}`}>
              <svg className={`w-3.5 h-3.5 ${STAT_COLORS.aliases.icon}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" /></svg>
              <span className="text-xs text-[#d4d4d4]">{skill.aliases.length} {t.aliases.toLowerCase()}</span>
            </div>
          )}

          <span className="text-white/10 mx-0.5">|</span>

          <button
            onClick={() => { setGraphMode('files'); openGraph('files'); }}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#52c7e8]/[0.06] border border-[#52c7e8]/20 text-xs font-medium text-[#52c7e8] hover:bg-[#52c7e8]/[0.12] transition-all cursor-pointer"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z" /></svg>
            {t.fileGraph}
          </button>
          <button
            onClick={() => { setGraphMode('knowledge'); openGraph('knowledge'); }}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#52c7e8]/[0.06] border border-[#52c7e8]/20 text-xs font-medium text-[#52c7e8] hover:bg-[#52c7e8]/[0.12] transition-all cursor-pointer"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" /></svg>
            {t.knowledgeMap}
          </button>

          <a
            href={`${OFFICIAL_STORE_REPO_URL}/tree/main/packages/${pkgId}/${skillId}`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/[0.03] border border-white/[0.06] text-xs text-[#8a8a8a] hover:text-[#52c7e8] hover:border-[#52c7e8]/20 transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/></svg>
            GitHub
          </a>
        </div>
      </div>

      {/* File tree */}
      {treeModules.length > 0 && (
        <div className="section-panel mt-5">
          <h3 className="text-sm font-semibold text-[#8a8a8a] uppercase tracking-wider mb-3">{t.fileTree}</h3>
          <div className="flex flex-wrap gap-1.5">
            {treeModules.map(filePath => {
              const fileName = filePath.split('/').pop() || filePath;
              const isTtl = filePath.endsWith('.ttl');
              const isMain = filePath === `${skillId}/ontoskill.ttl`;
              const color = getNodeColor(isMain ? 'main' : 'module', isMain);
              if (isTtl) return (
                <button
                  key={filePath}
                  onClick={() => openFileKnowledgeMap(filePath)}
                  className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.06] text-sm text-[#d4d4d4] hover:border-[#52c7e8]/30 hover:text-[#52c7e8] hover:bg-[#52c7e8]/[0.04] transition-all cursor-pointer group"
                >
                  <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: color }} />
                  <span className="font-mono text-xs">{fileName}</span>
                  <svg className="w-3 h-3 text-[#666] group-hover:text-[#52c7e8] transition-colors shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" /></svg>
                </button>
              );
              return (
                <a
                  key={filePath}
                  href={`${TTL_BASE}${pkgId}/${filePath}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-white/[0.02] border border-white/[0.04] text-sm text-[#666] hover:text-[#8a8a8a] hover:border-white/[0.08] transition-all"
                >
                  <span className="w-1.5 h-1.5 rounded-full shrink-0 bg-white/20" />
                  <span className="font-mono text-xs">{fileName}</span>
                </a>
              );
            })}
          </div>
        </div>
      )}

      {/* Content: intents, dependencies, aliases — two columns */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {skill.intents.length > 0 && (
          <div className="section-panel">
            <h3 className="text-sm font-semibold text-[#8a8a8a] uppercase tracking-wider mb-3">{t.intents}</h3>
            <div className="flex flex-wrap gap-1.5">
              {skill.intents.map(intent => (
                <span key={intent} className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-[#dba32c]/[0.06] border border-[#dba32c]/20 text-sm text-[#d4d4d4]">
                  <svg className="w-3 h-3 text-[#dba32c] shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                  {intent}
                </span>
              ))}
            </div>
          </div>
        )}
        {skill.dependsOn.length > 0 && (
          <div className="section-panel">
            <h3 className="text-sm font-semibold text-[#8a8a8a] uppercase tracking-wider mb-3">{t.dependencies}</h3>
            <div className="flex flex-wrap gap-2">
              {skill.dependsOn.map(d => {
                const dep = skills.find(s => s.packageId === pkgId && s.skillId === d);
                if (!dep) return (
                  <span key={d} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/[0.03] text-sm text-[#8a8a8a]">
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.172 13.828a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.102 1.101" /></svg>
                    {d}
                  </span>
                );
                return (
                  <a key={d} href={`${prefix}/${dep.qualifiedId}`} onClick={navClick(`${prefix}/${dep.qualifiedId}`, navigate)} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/5 text-sm text-[#d4d4d4] hover:text-[#52c7e8] hover:bg-white/10 transition-colors">
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.172 13.828a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.102 1.101" /></svg>
                    {d}
                  </a>
                );
              })}
            </div>
          </div>
        )}
        {skill.aliases.length > 0 && (
          <div className="section-panel">
            <h3 className="text-sm font-semibold text-[#8a8a8a] uppercase tracking-wider mb-3">{t.aliases}</h3>
            <div className="flex flex-wrap gap-2">
              {skill.aliases.map(a => (
                <span key={a} className="px-3 py-1.5 rounded-lg bg-white/5 text-sm text-[#8a8a8a] border border-white/[0.06]">
                  {a}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </>
  );
}
