import { Line } from '@react-three/drei';

export function GraphEdgeLine({ start, end, sourceColor, targetColor }: { start: [number, number, number]; end: [number, number, number]; sourceColor?: string; targetColor?: string }) {
  if (!start.every(isFinite) || !end.every(isFinite)) return null;
  const midColor = sourceColor || targetColor || '#ffffff';
  return (
    <Line
      points={[start, end]}
      color={midColor}
      lineWidth={1.5}
      transparent
      opacity={0.25}
    />
  );
}
