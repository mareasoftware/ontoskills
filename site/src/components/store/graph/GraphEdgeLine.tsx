import { Line } from '@react-three/drei';
import { useMemo } from 'react';
import * as THREE from 'three';

export function GraphEdgeLine({ start, end, sourceColor, targetColor, directed }: { start: [number, number, number]; end: [number, number, number]; sourceColor?: string; targetColor?: string; directed?: boolean }) {
  if (!start.every(isFinite) || !end.every(isFinite)) return null;
  const midColor = sourceColor || targetColor || '#ffffff';
  const arrow = useMemo(() => {
    if (!directed) return null;
    const dir = new THREE.Vector3().subVectors(
      new THREE.Vector3(...end),
      new THREE.Vector3(...start),
    ).normalize();
    const pos = new THREE.Vector3(...start).lerp(new THREE.Vector3(...end), 0.75);
    const quat = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
    return { pos, quat };
  }, [start[0], start[1], start[2], end[0], end[1], end[2], directed]);
  return (
    <group>
      <Line points={[start, end]} color={midColor} lineWidth={1.5} transparent opacity={0.25} />
      {arrow && directed && (
        <mesh position={arrow.pos} quaternion={arrow.quat}>
          <coneGeometry args={[0.4, 1.2, 8]} />
          <meshStandardMaterial color={midColor} emissive={midColor} emissiveIntensity={0.3} transparent opacity={0.5} />
        </mesh>
      )}
    </group>
  );
}
