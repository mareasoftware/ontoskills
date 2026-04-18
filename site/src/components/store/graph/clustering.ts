import type { GraphNode, GraphEdge } from '../types';
import { CATEGORY_LABELS } from './colors';

export function clusterGraphData(nodes: GraphNode[], edges: GraphEdge[]): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const skillNodes = nodes.filter(n => n.category === 'skill');
  const nonSkillNodes = nodes.filter(n => n.category !== 'skill');

  const groups = new Map<string, GraphNode[]>();
  for (const node of nonSkillNodes) {
    const g = groups.get(node.category) || [];
    g.push(node);
    groups.set(node.category, g);
  }

  const result: GraphNode[] = [...skillNodes];
  const idMap = new Map<string, string>();

  for (const node of skillNodes) {
    idMap.set(node.id, node.id);
  }

  for (const [category, group] of groups) {
    const typeName = CATEGORY_LABELS[category]?.[0] || category;

    if (group.length === 1) {
      const node = group[0];
      result.push(node);
      idMap.set(node.id, node.id);
    } else {
      const clusterId = `cluster:${category}`;
      const mapped: GraphNode = {
        id: clusterId,
        label: typeName,
        category,
        qualifiedId: clusterId,
        isHighlighted: group.some(n => n.isHighlighted),
        isCluster: true,
        clusterNodes: group.map(n => ({ ...n, value: n.label })),
        count: group.length,
      };
      result.push(mapped);
      for (const n of group) {
        idMap.set(n.id, clusterId);
      }
    }
  }

  const seen = new Set<string>();
  const newEdges: GraphEdge[] = [];
  for (const e of edges) {
    const s = idMap.get(e.source);
    const t = idMap.get(e.target);
    if (!s || !t || s === t) continue;
    const key = `${s}→${t}`;
    if (seen.has(key)) continue;
    seen.add(key);
    newEdges.push({ source: s, target: t });
  }

  return { nodes: result, edges: newEdges };
}
