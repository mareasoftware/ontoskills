import { useRef, useMemo } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';

export function AutoRotate({ paused }: { paused?: boolean }) {
  const { camera } = useThree();
  useFrame(() => {
    if (paused) return;
    camera.position.applyAxisAngle(new THREE.Vector3(0, 1, 0), 0.0006);
    camera.lookAt(0, 0, 0);
  });
  return null;
}

export function CameraFocus({ target, active }: { target: [number, number, number]; active: boolean }) {
  const { camera } = useThree();
  const targetVec = useRef(new THREE.Vector3(...target));
  targetVec.current.set(...target);
  useFrame(() => {
    if (!active) return;
    const desired = new THREE.Vector3(target[0] + 14, target[1] + 10, target[2] + 14);
    camera.position.lerp(desired, 0.04);
    camera.lookAt(targetVec.current);
  });
  return null;
}

export function BackgroundParticles() {
  const count = 150;
  const positions = useMemo(() => {
    const arr = new Float32Array(count * 3);
    let seed = 42;
    const rand = () => { seed = (seed * 16807) % 2147483647; return (seed - 1) / 2147483646; };
    for (let i = 0; i < count * 3; i++) arr[i] = (rand() - 0.5) * 120;
    return arr;
  }, []);
  return (
    <points>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" count={count} array={positions} itemSize={3} />
      </bufferGeometry>
      <pointsMaterial color="#52c7e8" size={0.08} transparent opacity={0.2} blending={THREE.AdditiveBlending} depthWrite={false} />
    </points>
  );
}
