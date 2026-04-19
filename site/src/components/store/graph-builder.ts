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

export function buildAuthorGraphData(skillList: Skill[], authorId: string) {
  const authorSkills = skillList.filter(s => s.author === authorId);
  const pkgIds = [...new Set(authorSkills.map(s => s.packageId))];
  const nodes: GraphNode[] = [
    { id: 'author', label: authorId, category: 'author', qualifiedId: authorId, isHighlighted: false },
  ];
  const edges: GraphEdge[] = [];
  for (const pid of pkgIds) {
    const pkgName = pid.split('/').slice(1).join('/');
    const pkgSkills = authorSkills.filter(s => s.packageId === pid);
    const cats = [...new Set(pkgSkills.map(s => s.category).filter(Boolean))];
    nodes.push({
      id: pid,
      label: pkgName,
      category: 'package',
      qualifiedId: pid,
      isHighlighted: false,
      count: pkgSkills.length,
      description: cats.join(', '),
    });
    edges.push({ source: 'author', target: pid });
  }
  return { nodes, edges };
}
