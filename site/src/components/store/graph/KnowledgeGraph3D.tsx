import { useState, useMemo } from 'react';
import { Canvas } from '@react-three/fiber';
import type { GraphNode, GraphEdge, Translations } from '../types';
import { getNodeColor, CATEGORY_LABELS, CATEGORY_DESCRIPTIONS } from './colors';
import { Scene } from './Scene';
import { GraphErrorBoundary } from '../components/GraphErrorBoundary';

export function KnowledgeGraph3D({ nodes, edges, onNodeClick, onBackgroundClick, height = 350, highlightCategory, onHighlightCategory, t, hideLabels }: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  onNodeClick: (node: GraphNode) => void;
  onBackgroundClick?: () => void;
  height?: number | string;
  highlightCategory?: string | null;
  onHighlightCategory?: (cat: string | null) => void;
  t: Translations;
  hideLabels?: boolean;
}) {
  const [legendExpanded, setLegendExpanded] = useState(false);
  const [shortcutsVisible, setShortcutsVisible] = useState(false);

  if (!nodes.length) return null;
  const R = 5 + Math.sqrt(nodes.length) * 4;
  const viewH = typeof window !== 'undefined' ? window.innerHeight : 800;
  const fovScale = viewH < 600 ? 0.7 : viewH < 900 ? 0.85 : 1;
  const camDist = Math.max(R * 3 * fovScale, 25);
  const cats = useMemo(() => [...new Set(nodes.map(n => n.category))], [nodes]);

  return (
    <div className="relative" style={{ width: '100%', height, borderRadius: '0.5rem', overflow: 'hidden', background: 'rgba(0,0,0,0.3)', cursor: 'grab' }}>
      <GraphErrorBoundary>
      <Canvas camera={{ position: [0, 0, camDist], fov: 55 }} gl={{ alpha: true, antialias: true }} onPointerMissed={onBackgroundClick}>
        <Scene
          nodes={nodes}
          edges={edges}
          onNodeClick={onNodeClick}
          highlightCategory={highlightCategory}
          focusNodeId={undefined}
          hideLabels={hideLabels}
          clusterLabel={t.clusterInstances}
          exploreLabel={t.clickToExplore}
        />
      </Canvas>
      </GraphErrorBoundary>
      {cats.length > 1 && (
        <div className="absolute bottom-3 left-3 z-10 max-w-[calc(100%-3rem)]">
          <div className="rounded-lg border border-white/[0.08] bg-[#090909]/90 backdrop-blur-md overflow-hidden">
            <div className="flex items-center gap-2 px-3 py-2 overflow-x-auto scrollbar-none">
              <span className="text-xs uppercase tracking-wider text-[#8a8a8a] shrink-0">{t.legend}</span>
              {cats.map(c => {
                const color = getNodeColor(c, false);
                const label = CATEGORY_LABELS[c]?.[0] || c;
                return (
                  <button
                    key={c}
                    onClick={() => onHighlightCategory?.(highlightCategory === c ? null : c)}
                    className={`w-5 h-5 rounded-full border-2 transition-all duration-150 shrink-0 ${highlightCategory === c ? 'scale-125 border-white/40' : 'border-transparent hover:scale-110'}`}
                    style={{ background: color }}
                    title={label}
                  />
                );
              })}
              <button onClick={() => setLegendExpanded(!legendExpanded)} aria-label={legendExpanded ? t.controls : t.legend} aria-expanded={legendExpanded} className="shrink-0 ml-0.5 text-[#8a8a8a] hover:text-[#d4d4d4] transition-colors">
                <svg className={`w-4 h-4 transition-transform ${legendExpanded ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
              </button>
            </div>
            {legendExpanded && (
              <div className="border-t border-white/[0.06] px-3 py-3 space-y-2 max-h-[50vh] overflow-y-auto">
                {cats.map(c => {
                  const color = getNodeColor(c, false);
                  const label = CATEGORY_LABELS[c]?.[0] || c;
                  return (
                    <div key={c} className="flex items-start gap-2">
                      <span className="w-3 h-3 rounded-full mt-0.5 shrink-0" style={{ background: color }} />
                      <div>
                        <span className="text-xs font-medium text-[#d4d4d4]">{label}</span>
                        <p className="text-[11px] text-[#8a8a8a] leading-relaxed">{CATEGORY_DESCRIPTIONS[c] || ''}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
      <div className="absolute top-4 right-4 text-sm text-[#8a8a8a] z-10">
        {nodes.length} {nodes.length === 1 ? t.node_one : t.node_other} · {edges.length} {edges.length === 1 ? t.edge_one : t.edge_other}
      </div>
      <div className="absolute bottom-3 right-3 z-10">
        <div className="relative">
          <button
            onClick={() => setShortcutsVisible(!shortcutsVisible)}
            className="w-7 h-7 rounded-full bg-white/[0.04] border border-white/[0.08] text-[#8a8a8a] text-xs hover:bg-white/[0.08] hover:text-[#d4d4d4] transition-colors flex items-center justify-center"
          >
            ?
          </button>
          {shortcutsVisible && (
            <div className="absolute bottom-9 right-0 w-44 rounded-lg bg-[#090909]/95 backdrop-blur-md border border-white/[0.08] p-3 text-[11px] text-[#8a8a8a] space-y-1.5">
              <p className="text-[#d4d4d4] font-medium mb-1">{t.controls}</p>
              <p>{t.ctrlZoom}</p>
              <p>{t.ctrlOrbit}</p>
              <p>{t.ctrlPan}</p>
              <p>{t.ctrlDetails}</p>
              <p>{t.ctrlClose}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
