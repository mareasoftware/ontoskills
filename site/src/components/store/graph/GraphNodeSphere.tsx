import { useRef, useState, memo } from 'react';
import { Html, Text, Billboard } from '@react-three/drei';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import type { GraphNode } from '../types';
import { getNodeColor, CATEGORY_LABELS } from './colors';


/** Text that scales fontSize with camera distance so labels stay readable. */
function DistanceScaledText({ position, baseFontSize, children, ...props }: {
  position: [number, number, number];
  baseFontSize: number;
  children: string;
} & Omit<React.ComponentProps<typeof Text>, 'fontSize' | 'position'>) {
  const { camera } = useThree();
  const [fontSize, setFontSize] = useState(baseFontSize);
  useFrame(() => {
    const d = camera.position.distanceTo(new THREE.Vector3(...position));
    const target = baseFontSize * Math.max(1, d / 25);
    setFontSize(prev => Math.abs(prev - target) > 0.02 ? THREE.MathUtils.lerp(prev, target, 0.15) : prev);
  });
  return <Text fontSize={fontSize} {...props}>{children}</Text>;
}

export const GraphNodeSphere = memo(function GraphNodeSphere({ node, position, onClick, dimmed = false, hideLabel = false, clusterLabel, exploreLabel, lowDetail = false }: {
  node: GraphNode;
  position: [number, number, number];
  onClick: (node: GraphNode) => void;
  dimmed?: boolean;
  hideLabel?: boolean;
  clusterLabel?: string;
  exploreLabel?: string;
  lowDetail?: boolean;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const [hovered, setHovered] = useState(false);
  const color = getNodeColor(node.category, node.isHighlighted);
  const isCluster = !!node.isCluster;
  const clusterCount = node.count || 0;

  const baseRadius = node.isHighlighted ? 1.4 : 0.9;
  const radius = isCluster ? baseRadius * (1 + Math.min(clusterCount * 0.15, 0.8)) : baseRadius;
  const segments = lowDetail ? 8 : 16;
  const showGlow = node.isHighlighted && !dimmed && !lowDetail;

  const isExplorable = !isCluster && ['main', 'prompt', 'test', 'module'].includes(node.category) && node.qualifiedId.endsWith('.ttl');
  const categoryLabel = CATEGORY_LABELS[node.category]?.[0] || node.category;
  const displayLabel = node.label.length > 24 ? node.label.slice(0, 22) + '…' : node.label;

  return (
    <group position={position}>
      {showGlow && (
        <mesh>
          <sphereGeometry args={[radius * 2.5, 8, 8]} />
          <meshBasicMaterial color={color} transparent opacity={0.08} />
        </mesh>
      )}
      <mesh
        ref={meshRef}
        onClick={(e) => { e.stopPropagation(); onClick(node); }}
        onPointerOver={(e) => { e.stopPropagation(); setHovered(true); }}
        onPointerOut={() => { setHovered(false); }}
      >
        <sphereGeometry args={[radius, segments, segments]} />
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
      {isCluster && !dimmed && (
        <Billboard position={[0, radius + 0.35, 0]}>
          <DistanceScaledText
            position={position}
            baseFontSize={0.35}
            color={color}
            anchorX="center"
            anchorY="middle"
            outlineWidth={0.12}
            outlineColor="#000000"
          >
            {`\u00d7${clusterCount}`}
          </DistanceScaledText>
        </Billboard>
      )}
      {!hideLabel && (
        <Billboard position={[0, -(radius + 0.55), 0]}>
          <DistanceScaledText
            position={position}
            baseFontSize={0.3}
            color="#e0e0e0"
            fillOpacity={dimmed ? 0.12 : 1}
            outlineWidth={dimmed ? 0 : 0.12}
            outlineColor="#000000"
            anchorX="center"
            anchorY="top"
            onPointerOver={(e) => { e.stopPropagation(); setHovered(true); }}
            onPointerOut={() => setHovered(false)}
            onClick={(e) => { e.stopPropagation(); onClick(node); }}
          >
            {displayLabel}
          </DistanceScaledText>
        </Billboard>
      )}
      {hovered && !dimmed && (
        <Html position={[0, radius + (isCluster ? 1.4 : 1.2), 0]} center zIndexRange={[200, 150]}>
          <div
            onClick={() => onClick(node)}
            style={{
              background: 'rgba(9, 9, 9, 0.95)',
              backdropFilter: 'blur(8px)',
              WebkitBackdropFilter: 'blur(8px)',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: '8px',
              padding: '8px 12px',
              whiteSpace: 'nowrap',
              pointerEvents: 'auto',
              cursor: 'pointer',
            }}
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
                  <div style={{ fontSize: '10px', color: '#52c7e8', marginTop: '6px' }}>{exploreLabel ?? 'Click to explore \u2192'}</div>
                )}
              </>
            )}
          </div>
        </Html>
      )}
    </group>
  );
});
