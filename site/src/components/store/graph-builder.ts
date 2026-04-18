import type { Skill, GraphNode, GraphEdge } from './types';

export function buildGraphData(skillList: Skill[], highlightId: string | null = null) {
  const idSet = new Set(skillList.map(s => s.skillId));
  const nodes: GraphNode[] = skillList.map(s => ({
    id: s.qualifiedId,
    label: s.skillId,
    category: s.category,
    qualifiedId: s.qualifiedId,
    isHighlighted: s.skillId === highlightId,
  }));
  const edges: GraphEdge[] = [];
  for (const s of skillList) {
    for (const d of s.dependsOn) {
      if (d !== s.skillId && idSet.has(d)) edges.push({ source: s.qualifiedId, target: `${s.packageId}/${d}` });
    }
  }
  return { nodes, edges };
}

export function packageHasDeps(skillList: Skill[]) {
  const idSet = new Set(skillList.map(s => s.skillId));
  return skillList.some(s => s.dependsOn.some(d => idSet.has(d)));
}

export function buildFileGraphData(modules: string[], skillId: string) {
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];
  const mainFile = `${skillId}/ontoskill.ttl`;
  const skillModules = modules.filter(m => m.startsWith(skillId + '/'));

  for (const m of skillModules) {
    const fileName = m.split('/').pop() || m;
    const isMain = m === mainFile;
    nodes.push({
      id: m,
      label: fileName,
      category: isMain ? 'main' : fileName.includes('test') ? 'test' : fileName.includes('prompt') ? 'prompt' : 'module',
      qualifiedId: m,
      isHighlighted: isMain,
    });
    if (!isMain && skillModules.includes(mainFile)) {
      edges.push({ source: mainFile, target: m });
    }
  }
  return { nodes, edges };
}
