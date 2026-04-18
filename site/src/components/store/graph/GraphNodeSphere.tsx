import { useRef, useState, type CSSProperties } from 'react';
import { Html } from '@react-three/drei';
import * as THREE from 'three';
import type { GraphNode } from '../types';
import { getNodeColor } from './colors';
import { CATEGORY_LABELS } from './colors';

export function GraphNodeSphere({ node, position, onClick, dimmed = false, hideLabel = false, clusterLabel, exploreLabel }: {
  node: GraphNode;
  position: [number, number, number];
  onClick: (node: GraphNode) => void;
  dimmed?: boolean;
  hideLabel?: boolean;
  clusterLabel?: string;
  exploreLabel?: string;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const [hovered, setHovered] = useState(false);
  const color = getNodeColor(node.category, node.isHighlighted);
  const isCluster = !!node.isCluster;
  const clusterCount = node.count || 0;

  const baseRadius = node.isHighlighted ? 1.4 : 0.9;
  const radius = isCluster ? baseRadius * (1 + Math.min(clusterCount * 0.15, 0.8)) : baseRadius;

  const isExplorable = !isCluster && ['main', 'prompt', 'test', 'module'].includes(node.category) && node.qualifiedId.endsWith('.ttl');
  const categoryLabel = CATEGORY_LABELS[node.category]?.[0] || node.category;

  const labelStyle: CSSProperties = {
    fontSize: '12px',
    fontWeight: 600,
    fontFamily: "'Inter Variable', 'Inter', system-ui, sans-serif",
    color: dimmed ? 'rgba(224,224,224,0.12)' : '#e0e0e0',
    background: 'rgba(9, 9, 9, 0.75)',
    padding: '3px 8px',
    borderRadius: '4px',
    border: '1px solid rgba(255,255,255,0.06)',
    backdropFilter: 'blur(4px)',
    WebkitBackdropFilter: 'blur(4px)',
    whiteSpace: 'nowrap' as const,
    userSelect: 'none',
    textShadow: '0 1px 2px rgba(0,0,0,0.5)',
    maxWidth: '180px',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    transition: 'opacity 0.3s',
    opacity: dimmed ? 0.12 : 1,
  };

  const tooltipStyle: CSSProperties = {
    background: 'rgba(9, 9, 9, 0.95)',
    backdropFilter: 'blur(8px)',
    WebkitBackdropFilter: 'blur(8px)',
    border: '1px solid rgba(255,255,255,0.1)',
    borderRadius: '8px',
    padding: '8px 12px',
    whiteSpace: 'nowrap' as const,
    pointerEvents: 'none',
  };

  return (
    <group position={position}>
      {node.isHighlighted && !dimmed && (
        <mesh>
          <sphereGeometry args={[radius * 2.5, 32, 32]} />
          <meshBasicMaterial color={color} transparent opacity={0.08} />
        </mesh>
      )}
      <mesh
        ref={meshRef}
        onClick={(e) => { e.stopPropagation(); onClick(node); }}
        onPointerOver={(e) => { e.stopPropagation(); setHovered(true); }}
        onPointerOut={() => { setHovered(false); }}
      >
        <sphereGeometry args={[radius, 32, 32]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={hovered && !dimmed ? 0.6 : node.isHighlighted && !dimmed ? 0.4 : 0.15}
          roughness={0.3}
          metalness={0.2}
          transparent
          opacity={dimmed ? 0.12 : 0.9}
        />
      </mesh>
      {/* Cluster count badge */}
      {isCluster && !dimmed && (
        <Html position={[0, radius + 0.3, 0]} center zIndexRange={[10, 0]}>
          <div style={{
            background: 'rgba(9, 9, 9, 0.85)',
            border: `1px solid ${color}40`,
            borderRadius: '10px',
            padding: '1px 6px',
            fontSize: '10px',
            fontWeight: 700,
            color,
            lineHeight: '16px',
            pointerEvents: 'none',
          }}>
            ×{clusterCount}
          </div>
        </Html>
      )}
      {!hideLabel && (
        <Html
          position={[0, -(radius + 0.5), 0]}
          center
          zIndexRange={[5, 0]}
        >
          <div
            style={{ ...labelStyle, pointerEvents: 'auto', cursor: 'pointer' }}
            onClick={(e) => { e.stopPropagation(); onClick(node); }}
          >
            {node.label}
          </div>
        </Html>
      )}
      {hovered && !dimmed && (
        <Html position={[0, radius + (isCluster ? 1.4 : 1.2), 0]} center zIndexRange={[15, 0]}>
          <div
            onClick={() => onClick(node)}
            style={{ ...tooltipStyle, pointerEvents: 'auto', cursor: 'pointer' }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
              <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: color, display: 'inline-block' }} />
              <span style={{ fontSize: '13px', fontWeight: 600, color: '#f5f5f5' }}>{node.label}</span>
            </div>
            {isCluster ? (
              <span style={{ fontSize: '10px', color, fontWeight: 500 }}>
                {clusterCount} {clusterLabel ?? 'instances'}
              </span>
            ) : (
              <>
                <span style={{ fontSize: '10px', color: '#8a8a8a', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                  {categoryLabel}
                </span>
                {isExplorable && (
                  <div style={{ fontSize: '10px', color: '#52c7e8', marginTop: '6px' }}>{exploreLabel ?? 'Click to explore →'}</div>
                )}
              </>
            )}
          </div>
        </Html>
      )}
    </group>
  );
}
