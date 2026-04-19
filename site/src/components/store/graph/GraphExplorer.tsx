import { useState, useEffect, useMemo, useCallback, useRef, lazy, Suspense } from 'react';
import type { Skill, PackageManifest, GraphNode, GraphEdge, GraphLevel, Translations } from '../types';
import { buildGraphData, buildFileGraphData, buildAuthorGraphData } from '../graph-builder';
import { parseTtlKnowledgeMap } from '../ttl-parser';
import { TTL_BASE } from '../helpers';
import { clusterGraphData } from './clustering';
import { GraphLoader } from '../components/GraphLoader';
import { NodeDetailPanel } from '../views/NodeDetailPanel';

const KnowledgeGraph3D = lazy(() => import('./KnowledgeGraph3D').then(m => ({ default: m.KnowledgeGraph3D })));

export interface GraphExplorerProps {
  skills: Skill[];
  packages: PackageManifest[];
  initialLevel: GraphLevel;
  t: Translations;
  prefix: string;
  navigate: (href: string) => void;
  onClose: () => void;
}

export function GraphExplorer({ skills, packages, initialLevel, t, prefix, navigate, onClose }: GraphExplorerProps) {
  const [stack, setStack] = useState<GraphLevel[]>([initialLevel]);
  const currentLevel = stack[stack.length - 1];
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [highlightCategory, setHighlightCategory] = useState<string | null>(null);
  const [knowledgeData, setKnowledgeData] = useState<{ nodes: GraphNode[]; edges: GraphEdge[] } | null>(null);
  const [loadingKnowledge, setLoadingKnowledge] = useState(false);
  const [graphError, setGraphError] = useState(false);
  const [graphMode, setGraphMode] = useState<'files' | 'knowledge'>(
    currentLevel.type === 'skill' ? currentLevel.mode : 'files'
  );
  const abortRef = useRef<AbortController | null>(null);

  // Lock body scroll
  useEffect(() => {
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = ''; };
  }, []);

  // Reset state when level changes
  useEffect(() => {
    setSelectedNode(null);
    setHighlightCategory(null);
    setGraphError(false);
    if (currentLevel.type === 'skill') {
      setGraphMode(currentLevel.mode);
    } else {
      setGraphMode('files');
    }
  }, [currentLevel]);

  // Abort controller
  useEffect(() => {
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    return () => { ac.abort(); };
  }, [currentLevel]);

  const pushLevel = useCallback((level: GraphLevel) => {
    setStack(prev => [...prev, level]);
    setKnowledgeData(null);
  }, []);

  const popToLevel = useCallback((index: number) => {
    setStack(prev => prev.slice(0, index + 1));
    setKnowledgeData(null);
  }, []);

  // --- Build graph data per level ---
  const authorGraphData = useMemo(() => {
    if (currentLevel.type !== 'author') return null;
    return buildAuthorGraphData(skills, currentLevel.authorId);
  }, [skills, currentLevel]);

  const packageGraphData = useMemo(() => {
    if (currentLevel.type !== 'package') return null;
    const pkgSkills = skills.filter(s => s.packageId === currentLevel.pkgId);
    const built = buildGraphData(pkgSkills);
    return { nodes: built.nodes, edges: built.edges.map(e => ({ ...e, directed: true })) };
  }, [skills, currentLevel]);

  const skillModules = useMemo(() => {
    if (currentLevel.type !== 'skill') return [];
    const rawPkg = packages.find(p => p.package_id === currentLevel.pkgId);
    const modules: string[] = rawPkg?.modules || [];
    const sid = currentLevel.skillId;
    const filtered = modules.filter(m => m.startsWith(sid + '/') || m === `${sid}/ontoskill.ttl`);
    return filtered.length ? filtered : modules.filter(m => m.startsWith(sid));
  }, [packages, currentLevel]);

  const fileGraphData = useMemo(() => {
    if (currentLevel.type !== 'skill') return null;
    return buildFileGraphData(skillModules, currentLevel.skillId);
  }, [skillModules, currentLevel]);

  const loadKnowledgeGraph = useCallback(async () => {
    if (currentLevel.type !== 'skill') return;
    setLoadingKnowledge(true);
    setGraphError(false);
    try {
      const ttlBase = `${TTL_BASE}${currentLevel.pkgId}/`;
      const ttlFiles = skillModules.filter(m => m.endsWith('.ttl'));
      const contents: string[] = [];
      await Promise.all(ttlFiles.map(async (f) => {
        try {
          const res = await fetch(ttlBase + f, { signal: abortRef.current?.signal });
          if (res.ok) contents.push(await res.text());
        } catch (e: any) { if (e.name === 'AbortError') throw e; }
      }));
      if (!contents.length) { setGraphError(true); return; }
      setKnowledgeData(parseTtlKnowledgeMap(contents.join('\n'), currentLevel.skillId));
    } catch (e: any) { if (e.name !== 'AbortError') setGraphError(true); }
    finally { setLoadingKnowledge(false); }
  }, [currentLevel, skillModules]);

  const clusteredKnowledgeData = useMemo(() => knowledgeData ? clusterGraphData(knowledgeData.nodes, knowledgeData.edges) : null, [knowledgeData]);

  // Effective graph data
  let displayData: { nodes: GraphNode[]; edges: GraphEdge[] } | null = null;
  if (currentLevel.type === 'author') displayData = authorGraphData;
  else if (currentLevel.type === 'package') displayData = packageGraphData;
  else if (graphMode === 'files') displayData = fileGraphData;
  else displayData = clusteredKnowledgeData ?? null;

  // --- onNodeClick per level ---
  const handleNodeClick = useCallback((node: GraphNode) => {
    if (node.id === 'author') { setSelectedNode(node); return; }
    if (currentLevel.type === 'author' && node.category === 'package') {
      pushLevel({ type: 'package', authorId: currentLevel.authorId, pkgId: node.qualifiedId });
      return;
    }
    if (currentLevel.type === 'package') {
      const skill = skills.find(s => s.packageId === currentLevel.pkgId && s.qualifiedId === node.id);
      if (skill) {
        pushLevel({ type: 'skill', pkgId: currentLevel.pkgId, skillId: skill.skillId, mode: 'files' });
        return;
      }
    }
    setSelectedNode(node);
  }, [currentLevel, skills, pushLevel]);

  const handleExploreFile = useCallback(async (node: GraphNode) => {
    if (currentLevel.type !== 'skill') return;
    const fileId = node.qualifiedId;
    if (!fileId.endsWith('.ttl')) return;
    setLoadingKnowledge(true);
    setGraphError(false);
    setSelectedNode(null);
    try {
      const res = await fetch(`${TTL_BASE}${currentLevel.pkgId}/${fileId}`, { signal: abortRef.current?.signal });
      if (!res.ok) throw new Error(`Failed: ${res.status}`);
      const content = await res.text();
      setKnowledgeData(parseTtlKnowledgeMap(content, fileId.split('/').pop()!.replace('.ttl', '')));
      setGraphMode('knowledge');
    } catch (e: any) { if (e.name !== 'AbortError') setGraphError(true); }
    finally { setLoadingKnowledge(false); }
  }, [currentLevel]);

  // --- Breadcrumb labels ---
  const breadcrumbLabels = useMemo(() => {
    return stack.map(level => {
      if (level.type === 'author') return level.authorId;
      if (level.type === 'package') return level.pkgId.split('/').slice(1).join('/');
      return level.skillId;
    });
  }, [stack]);

  const levelLabels: Record<string, string> = {
    author: t.authorGraph,
    package: t.packageGraph,
    skill: t.skillGraph,
  };

  const currentPkgId = currentLevel.type === 'author' ? '' : currentLevel.pkgId;

  return (
    <div
      className="fixed inset-0 z-50 bg-[#090909] flex flex-col overflow-hidden"
      onKeyDown={(e) => { if (e.key === 'Escape') onClose(); }}
      tabIndex={-1}
      ref={(el) => { if (el && !el.contains(document.activeElement)) el.focus(); }}
    >
      {/* Header: breadcrumb + controls */}
      <div className="flex items-center justify-between px-4 sm:px-6 py-3 border-b border-white/10 gap-3">
        <div className="flex flex-wrap items-center gap-2 min-w-0">
          {stack.map((level, i) => (
            <span key={i} className="flex items-center gap-1.5 text-xs shrink-0">
              {i > 0 && <svg className="w-3 h-3 text-[#8a8a8a]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>}
              <button
                onClick={() => { if (i < stack.length - 1) popToLevel(i); }}
                className={`transition-colors truncate max-w-[120px] ${i === stack.length - 1 ? 'text-[#f5f5f5] font-medium' : 'text-[#8a8a8a] hover:text-[#52c7e8]'}`}
              >
                {breadcrumbLabels[i]}
              </button>
            </span>
          ))}
          <span className="text-[#8a8a8a] text-xs">·</span>
          <span className="text-xs text-[#52c7e8]">{levelLabels[currentLevel.type]}</span>
          {currentLevel.type === 'skill' && (
            <div className="flex gap-1 bg-white/5 rounded-lg p-0.5">
              <button onClick={() => setGraphMode('files')} className={`px-2.5 py-1 rounded-md text-xs transition-colors ${graphMode === 'files' ? 'bg-[#52c7e8]/20 text-[#52c7e8]' : 'text-[#8a8a8a] hover:text-[#d4d4d4]'}`}>{t.fileGraph}</button>
              <button onClick={async () => { setGraphMode('knowledge'); if (!knowledgeData) await loadKnowledgeGraph(); }} className={`px-2.5 py-1 rounded-md text-xs transition-colors ${graphMode === 'knowledge' ? 'bg-[#52c7e8]/20 text-[#52c7e8]' : 'text-[#8a8a8a] hover:text-[#d4d4d4]'}`}>{t.knowledgeMap}</button>
            </div>
          )}
        </div>
        <button onClick={onClose} className="p-2 rounded-lg hover:bg-white/10 text-[#8a8a8a] hover:text-[#f5f5f5] transition-colors shrink-0" aria-label="Close">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
        </button>
      </div>

      {/* Graph canvas */}
      <div className="flex-1 relative">
        {loadingKnowledge ? (
          <div className="flex items-center justify-center h-full gap-3">
            <div className="w-5 h-5 border-2 border-[#52c7e8]/30 border-t-[#52c7e8] rounded-full animate-spin" />
            <p className="text-[#8a8a8a] text-sm">{t.loadingGraph}</p>
          </div>
        ) : graphError ? (
          <div className="flex items-center justify-center h-full"><p className="text-[#f9a8d4]">{t.graphError}</p></div>
        ) : (
          <Suspense fallback={<GraphLoader t={t} />}>
            {displayData ? (
              <KnowledgeGraph3D nodes={displayData.nodes} edges={displayData.edges} onNodeClick={handleNodeClick} onBackgroundClick={() => setSelectedNode(null)} highlightCategory={highlightCategory} onHighlightCategory={setHighlightCategory} height="100%" t={t} hideLabels={!!selectedNode} />
            ) : (
              <div className="flex items-center justify-center h-full"><p className="text-[#8a8a8a] text-sm">{t.graphError}</p></div>
            )}
          </Suspense>
        )}
        {selectedNode && displayData && (
          <NodeDetailPanel node={selectedNode} skills={skills} pkgId={currentPkgId} prefix={prefix} edges={displayData.edges} allNodes={displayData.nodes} t={t} onSelectNode={setSelectedNode} onExploreFile={handleExploreFile} onNavigate={navigate} onCloseGraph={onClose} />
        )}
      </div>
    </div>
  );
}
