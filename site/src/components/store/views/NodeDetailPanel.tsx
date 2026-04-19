import type { Skill, PackageManifest, GraphNode, GraphEdge, GraphLevel, Translations } from '../types';
import { getNodeColor, getConnectedNodes, CATEGORY_LABELS, CATEGORY_DESCRIPTIONS } from '../graph/colors';

interface NodeDetailPanelProps {
  node: GraphNode;
  skills: Skill[];
  packages: PackageManifest[];
  pkgId: string;
  prefix: string;
  edges: GraphEdge[];
  allNodes: GraphNode[];
  currentLevel: GraphLevel;
  t: Translations;
  onSelectNode: (node: GraphNode | null) => void;
  onExploreFile: (node: GraphNode) => void;
  onPushLevel: (level: GraphLevel) => void;
  onNavigate: (href: string) => void;
  onCloseGraph: () => void;
}

export function NodeDetailPanel({ node, skills, packages, pkgId, prefix, edges, allNodes, currentLevel, t, onSelectNode, onExploreFile, onPushLevel, onNavigate, onCloseGraph }: NodeDetailPanelProps) {
  const connected = getConnectedNodes(node, edges, allNodes);
  const isTtlFile = ['main', 'prompt', 'test', 'module'].includes(node.category) && node.qualifiedId.endsWith('.ttl');
  const rawId = node.id.replace(/^dep:/, '').replace(/_/g, '-');
  const depSkill = skills.find(s => s.packageId === pkgId && s.skillId === rawId);

  // Determine if this node can drill down to a deeper level
  const canDrillToPackage = currentLevel.type === 'author' && node.category === 'package' && node.id !== 'author';
  const canDrillToSkill = currentLevel.type === 'package';
  const drillSkill = canDrillToSkill ? skills.find(s => s.packageId === currentLevel.pkgId && s.qualifiedId === node.id) : null;
  const canDrill = canDrillToPackage || !!drillSkill;

  // For author-level package nodes, compute package info
  const pkgSkillCount = canDrillToPackage ? skills.filter(s => s.packageId === node.qualifiedId).length : 0;

  // Drill-down handler
  const handleDrillDown = () => {
    onSelectNode(null);
    if (canDrillToPackage) {
      onPushLevel({ type: 'package', authorId: currentLevel.authorId, pkgId: node.qualifiedId });
    } else if (drillSkill) {
      onPushLevel({ type: 'skill', pkgId: currentLevel.pkgId, skillId: drillSkill.skillId, mode: 'files' });
    }
  };

  // "View in page" handler — navigate to the skill's page (closes graph)
  const handleViewInPage = () => {
    const viewSkill = drillSkill ?? depSkill;
    if (viewSkill) {
      onCloseGraph();
      onSelectNode(null);
      onNavigate(`${prefix}/${viewSkill.qualifiedId}`);
    }
  };

  return (
    <div className="absolute sm:right-0 sm:top-0 sm:bottom-0 sm:left-auto sm:w-[360px] bottom-0 left-0 right-0 sm:max-h-none max-h-[60vh] bg-[#0d0d14]/95 backdrop-blur-md sm:border-l border-t border-white/[0.08] overflow-y-auto z-20" style={{ animation: 'slideIn 0.25s ease-out' }}>
      {/* Header */}
      <div className="px-5 pt-5 pb-4 border-b border-white/[0.07]">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full" style={{ background: getNodeColor(node.category, node.isHighlighted) }} />
            <span className="text-sm font-semibold text-[#f5f5f5]">{CATEGORY_LABELS[node.category]?.[0] || node.category}</span>
            {node.isCluster && node.count && (
              <span className="text-xs font-bold" style={{ color: getNodeColor(node.category, false) }}>×{node.count}</span>
            )}
            {canDrillToPackage && (
              <span className="text-xs text-[#8a8a8a]">{pkgSkillCount} {pkgSkillCount === 1 ? t.skill_one : t.skill_other}</span>
            )}
          </div>
          <button onClick={() => onSelectNode(null)} aria-label="Close" className="p-1.5 rounded-lg hover:bg-white/10 text-[#8a8a8a] transition-colors">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>
        {!node.isCluster && <p className="text-sm text-[#d4d4d4] mt-2 break-words leading-relaxed">{node.label}</p>}
        {node.isCluster && CATEGORY_DESCRIPTIONS[node.category] && <p className="text-xs text-[#666] mt-1">{CATEGORY_DESCRIPTIONS[node.category]}</p>}
      </div>

      {/* Cluster list */}
      {node.isCluster && node.clusterNodes && (
        <div className="px-5 py-4 border-b border-white/[0.05]">
          <div className="space-y-2">
            {node.clusterNodes.map((cn, i) => (
              <div key={cn.id || i} className="px-3 py-2.5 rounded-lg bg-white/[0.03] border border-white/[0.06] hover:border-white/[0.12] transition-colors">
                <div className="flex items-start gap-2">
                  <span className="w-2 h-2 rounded-full shrink-0 mt-1.5" style={{ background: getNodeColor(cn.category, cn.isHighlighted) }} />
                  <p className="text-sm text-[#d4d4d4] break-words leading-relaxed">{cn.description || cn.value || cn.label}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Description */}
      {!node.isCluster && node.description && (
        <div className="px-5 py-4 border-b border-white/[0.05]">
          <p className="text-sm text-[#d4d4d4] leading-relaxed break-words">{node.description}</p>
        </div>
      )}

      {/* Category-specific details */}
      {!node.isCluster && (() => {
        const detailId = node.qualifiedId || node.id;
        const depName = detailId.replace(/^dep:/, '').replace(/_/g, '-');
        const show = node.category === 'dependency' || node.value;
        return show ? (
          <div className="px-5 py-4 border-b border-white/[0.05]">
            <div className="space-y-2.5">
              {node.category === 'dependency' && (
                <div className="flex items-start gap-3">
                  <span className="text-xs text-[#8a8a8a] shrink-0 w-14">{t.skill_one}</span>
                  <span className="text-xs text-[#d4d4d4]">{depName}</span>
                </div>
              )}
              {node.value && !node.description && (
                <div className="flex items-start gap-3">
                  <span className="text-xs text-[#8a8a8a] shrink-0 w-14">{t.value}</span>
                  <code className="text-xs text-[#d4d4d4] font-mono break-all leading-relaxed">{node.value}</code>
                </div>
              )}
            </div>
          </div>
        ) : null;
      })()}

      {/* Connected nodes */}
      <div className="px-5 py-4 border-b border-white/[0.05]">
        <h3 className="text-xs uppercase tracking-widest text-[#8a8a8a] mb-3">{t.connectedTo}</h3>
        {!connected.length ? <p className="text-xs text-[#666]">{t.noConnections}</p> : (
          <div className="flex flex-wrap gap-2">
            {connected.map(n => (
              <button key={n.id} onClick={() => onSelectNode(n)} className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-white/[0.04] border border-white/[0.07] text-xs text-[#d4d4d4] hover:border-[#52c7e8]/30 hover:text-[#52c7e8] transition-colors">
                <span className="w-2 h-2 rounded-full shrink-0" style={{ background: getNodeColor(n.category, n.isHighlighted) }} />
                {n.label}
                {n.isCluster && n.count && <span className="text-[#8a8a8a]">×{n.count}</span>}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Actions */}
      {!node.isCluster && (
        <div className="px-5 py-4 space-y-2">
          {canDrill && (
            <button onClick={handleDrillDown} className="w-full py-2.5 rounded-lg bg-[#52c7e8]/10 text-[#52c7e8] text-sm font-medium hover:bg-[#52c7e8]/20 transition-colors flex items-center justify-center gap-2">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
              {canDrillToPackage ? t.exploreGraph : t.exploreGraph}
            </button>
          )}
          {isTtlFile && (
            <button onClick={() => onExploreFile(node)} className="w-full py-2.5 rounded-lg bg-[#52c7e8]/10 text-[#52c7e8] text-sm font-medium hover:bg-[#52c7e8]/20 transition-colors flex items-center justify-center gap-2">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
              {t.openKnowledgeMap}
            </button>
          )}
          {(depSkill || drillSkill) && (
            <button onClick={handleViewInPage} className="w-full py-2.5 rounded-lg bg-white/[0.04] border border-white/[0.07] text-sm text-[#d4d4d4] hover:border-[#52c7e8]/30 hover:text-[#52c7e8] transition-colors">
              {t.viewSkill}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
