import type { GraphNode, GraphEdge } from '../types';

export function layoutForce3D(nodes: GraphNode[], edges: GraphEdge[]) {
  const positions: Record<string, { x: number; y: number; z: number }> = {};
  const n = nodes.length;
  if (!n) return positions;
  const R = 12;
  nodes.forEach((node, i) => {
    const phi = Math.acos(1 - (2 * (i + 0.5)) / n);
    const theta = Math.PI * (1 + Math.sqrt(5)) * i;
    positions[node.id] = {
      x: R * Math.sin(phi) * Math.cos(theta),
      y: R * Math.sin(phi) * Math.sin(theta),
      z: R * Math.cos(phi),
    };
  });
  const iters = n > 100 ? 0 : Math.min(120, Math.max(30, Math.round(3000 / n)));
  for (let iter = 0; iter < iters; iter++) {
    const cooling = 0.1 * (1 - iter / iters);
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const a = positions[nodes[i].id], b = positions[nodes[j].id];
        const dx = a.x - b.x, dy = a.y - b.y, dz = a.z - b.z;
        const dist2 = dx * dx + dy * dy + dz * dz;
        const dist = Math.sqrt(Math.max(dist2, 0.01));
        const f = cooling / dist;
        a.x += dx * f; a.y += dy * f; a.z += dz * f;
        b.x -= dx * f; b.y -= dy * f; b.z -= dz * f;
      }
    }
    for (const e of edges) {
      const s = positions[e.source], t = positions[e.target];
      if (!s || !t) continue;
      const dx = t.x - s.x, dy = t.y - s.y, dz = t.z - s.z;
      const dist = Math.sqrt(Math.max(dx * dx + dy * dy + dz * dz, 0.01));
      const f = dist * 0.05 * cooling;
      s.x += (dx / dist) * f; s.y += (dy / dist) * f; s.z += (dz / dist) * f;
      t.x -= (dx / dist) * f; t.y -= (dy / dist) * f; t.z -= (dz / dist) * f;
    }
    for (const node of nodes) {
      const p = positions[node.id];
      const d = Math.sqrt(p.x * p.x + p.y * p.y + p.z * p.z);
      if (d > 25) { p.x *= 25 / d; p.y *= 25 / d; p.z *= 25 / d; }
    }
  }
  for (const node of nodes) {
    const p = positions[node.id];
    if (!isFinite(p.x)) p.x = 0;
    if (!isFinite(p.y)) p.y = 0;
    if (!isFinite(p.z)) p.z = 0;
  }
  return positions;
}
