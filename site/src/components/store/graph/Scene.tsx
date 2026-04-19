import { useMemo } from 'react';
import { OrbitControls } from '@react-three/drei';
import type { GraphNode, GraphEdge } from '../types';
import { getNodeColor } from './colors';
import { layoutForce3D } from './layout';
import { GraphNodeSphere } from './GraphNodeSphere';
import { GraphEdgeLine } from './GraphEdgeLine';
import { AutoRotate, CameraFocus, BackgroundParticles } from './CameraAuto';

export function Scene({ nodes, edges, onNodeClick, autoRotate = true, highlightCategory, focusNodeId, hideLabels, clusterLabel, exploreLabel }: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  onNodeClick: (node: GraphNode) => void;
  autoRotate?: boolean;
  highlightCategory?: string | null;
  focusNodeId?: string | null;
  hideLabels?: boolean;
  clusterLabel?: string;
  exploreLabel?: string;
}) {
  const positions = useMemo(() => layoutForce3D(nodes, edges), [nodes, edges]);
  const R = 5 + Math.sqrt(nodes.length) * 4;
  const largeGraph = nodes.length > 50;
  const focusNode = focusNodeId ? nodes.find(n => n.id === focusNodeId) : null;
  const focusPos = focusNode ? positions[focusNode.id] : null;

  return (
    <>
      <ambientLight intensity={0.5} />
      <pointLight position={[20, 20, 20]} intensity={1.5} color="#52c7e8" />
      <pointLight position={[-20, -10, 15]} intensity={0.8} color="#85f496" />
      <BackgroundParticles />
      {autoRotate && !focusNode && <AutoRotate />}
      {focusPos && isFinite(focusPos.x) && <CameraFocus target={[focusPos.x, focusPos.y, focusPos.z]} active={!!focusNode} />}
      <OrbitControls
        enableDamping
        dampingFactor={0.12}
        rotateSpeed={0.5}
        autoRotate={false}
        minDistance={Math.max(3, R * 0.3)}
        maxDistance={Math.max(R * 6, 60)}
      />
      {nodes.map(n => {
        const p = positions[n.id];
        if (!p || !isFinite(p.x) || !isFinite(p.y) || !isFinite(p.z)) return null;
        const dimmed = highlightCategory ? n.category !== highlightCategory : false;
        return (
          <GraphNodeSphere
            key={n.id}
            node={n}
            position={[p.x, p.y, p.z]}
            onClick={onNodeClick}
            dimmed={dimmed}
            hideLabel={hideLabels}
            clusterLabel={clusterLabel}
            exploreLabel={exploreLabel}
            lowDetail={largeGraph}
          />
        );
      })}
      {edges.map((e, i) => {
        const s = positions[e.source], t = positions[e.target];
        if (!s || !t) return null;
        const sNode = nodes.find(n => n.id === e.source);
        const tNode = nodes.find(n => n.id === e.target);
        return (
          <GraphEdgeLine
            key={i}
            start={[s.x, s.y, s.z]}
            end={[t.x, t.y, t.z]}
            sourceColor={sNode ? getNodeColor(sNode.category, sNode.isHighlighted) : '#ffffff'}
            targetColor={tNode ? getNodeColor(tNode.category, tNode.isHighlighted) : '#ffffff'}
            directed={e.directed}
          />
        );
      })}
    </>
  );
}
