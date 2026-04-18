import type { Skill, GraphNode, GraphEdge } from './types';
import type { MouseEvent } from 'react';
import { OFFICIAL_STORE_INDEX_URL } from '../../data/store';

export const STORE_INDEX_URL = OFFICIAL_STORE_INDEX_URL;
export const TTL_BASE = STORE_INDEX_URL.replace('index.json', 'packages/');

export function normSkill(pkg: any, skill: any): Skill {
  const qid = `${pkg.package_id}/${skill.id}`;
  const parts = qid.split('/');
  return {
    packageId: pkg.package_id,
    skillId: skill.id,
    qualifiedId: qid,
    description: skill.description || pkg.description || '',
    aliases: Array.isArray(skill.aliases) ? skill.aliases : [],
    trustTier: pkg.trust_tier || 'verified',
    installCommand: `npx ontoskills install ${qid}`,
    author: parts[0] || '',
    category: skill.category || '',
    intents: Array.isArray(skill.intents) ? skill.intents : [],
    dependsOn: Array.isArray(skill.depends_on_skills) ? skill.depends_on_skills : [],
    version: pkg.version || '',
    modules: Array.isArray(pkg.modules) ? pkg.modules : [],
  };
}

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

function escRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export function hashStr(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

export function navClick(href: string, navigate: (href: string) => void) {
  return (e: MouseEvent) => {
    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    navigate(href);
  };
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

export function parseTtlKnowledgeMap(ttlContent: string, skillId: string) {
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];
  const rootId = `skill:${skillId}`;
  const seen = new Set<string>();

  nodes.push({ id: rootId, label: skillId, category: 'skill', qualifiedId: skillId, isHighlighted: true });
  seen.add(rootId);

  const addNode = (id: string, label: string, category: string): GraphNode | null => {
    if (seen.has(id)) return null;
    seen.add(id);
    const node: GraphNode = { id, label, category, qualifiedId: id, isHighlighted: false };
    nodes.push(node);
    return node;
  };

  // Skill dependencies
  for (const m of ttlContent.matchAll(/oc:dependsOnSkill\s+oc:skill_([^\s;,]+)/g)) {
    const depId = `dep:${m[1]}`;
    addNode(depId, m[1].replace(/_/g, '-'), 'dependency');
    edges.push({ source: rootId, target: depId });
  }

  // Skill inheritance
  for (const m of ttlContent.matchAll(/oc:extends\s+oc:skill_([^\s;,]+)/g)) {
    const extId = `extends:${m[1]}`;
    addNode(extId, m[1].replace(/_/g, '-'), 'extends');
    edges.push({ source: rootId, target: extId });
  }

  // Skill mutual exclusion
  for (const m of ttlContent.matchAll(/oc:contradicts\s+oc:skill_([^\s;,]+)/g)) {
    const conId = `contradicts:${m[1]}`;
    addNode(conId, m[1].replace(/_/g, '-'), 'contradicts');
    edges.push({ source: rootId, target: conId });
  }

  // Knowledge nodes
  const knRefs = new Set<string>();
  for (const m of ttlContent.matchAll(/oc:(kn_[a-f0-9]+)/g)) {
    knRefs.add(m[1]);
  }
  for (const knId of knRefs) {
    const typeMatch = ttlContent.match(new RegExp(`oc:${escRegex(knId)}\\s+a\\s+oc:KnowledgeNode(?:,\\s*oc:(\\w+))?`));
    if (!typeMatch) continue;
    const knType = typeMatch[1] || 'KnowledgeNode';
    const ctxMatch = ttlContent.match(new RegExp(`oc:${escRegex(knId)}[\\s\\S]*?oc:appliesToContext\\s+"([^"]+)"`));
    const fullContext = ctxMatch ? ctxMatch[1] : '';
    const label = fullContext.length > 40 ? fullContext.slice(0, 40) + '…' : fullContext || knType.replace(/([A-Z])/g, ' $1').trim();
    const rationaleMatch = ttlContent.match(new RegExp(`oc:${escRegex(knId)}[\\s\\S]*?oc:hasRationale\\s+"([^"]+)"`));
    const description = [fullContext, rationaleMatch?.[1]].filter(Boolean).join(' — ') || undefined;
    const knNode = addNode(knId, label, knType);
    if (knNode) knNode.description = description;
    edges.push({ source: rootId, target: knId });
  }

  // States — yields and requires
  for (const m of ttlContent.matchAll(/oc:(yieldsState|requiresState)\s+oc:(\w+)/g)) {
    const stateId = `state:${m[2]}`;
    const stateLabel = m[2].replace(/([A-Z])/g, ' $1').trim();
    const stateNode = addNode(stateId, stateLabel, m[1] === 'yieldsState' ? 'yield' : 'require');
    if (stateNode) stateNode.description = m[1] === 'yieldsState' ? `Produced after ${stateLabel.toLowerCase()}` : `Required before execution`;
    edges.push({ source: rootId, target: stateId });
  }

  // Failure states
  for (const m of ttlContent.matchAll(/oc:handlesFailure\s+oc:(\w+)/g)) {
    const failId = `fail:${m[1]}`;
    addNode(failId, m[1].replace(/([A-Z])/g, ' $1').trim(), 'failure');
    edges.push({ source: rootId, target: failId });
  }

  // Intents
  for (const m of ttlContent.matchAll(/oc:resolvesIntent\s+"([^"]+)"/g)) {
    const intentId = `intent:${m[1]}`;
    addNode(intentId, m[1], 'intent');
    edges.push({ source: rootId, target: intentId });
  }

  // Allowed tools
  for (const m of ttlContent.matchAll(/oc:hasAllowedTool\s+"([^"]+)"/g)) {
    const toolId = `tool:${m[1]}`;
    addNode(toolId, m[1], 'tool');
    edges.push({ source: rootId, target: toolId });
  }

  // Constraints
  for (const m of ttlContent.matchAll(/oc:hasConstraint\s+"([^"]+)"/g)) {
    const cId = `constraint:${m[1]}`;
    const cLabel = m[1].length > 40 ? m[1].slice(0, 40) + '…' : m[1];
    addNode(cId, cLabel, 'constraint');
    edges.push({ source: rootId, target: cId });
  }

  // Requirements
  for (const m of ttlContent.matchAll(/oc:hasRequirement\s+\[?\s*[\s\S]*?oc:requirementValue\s+"([^"]+)"[\s\S]*?oc:isOptional\s+"?(true|false)"?/g)) {
    const reqId = `requirement:${m[1]}`;
    const reqNode = addNode(reqId, m[1], 'requirement');
    if (reqNode) reqNode.description = m[2] === 'true' ? 'Optional' : 'Required';
    edges.push({ source: rootId, target: reqId });
  }

  // Reference files
  for (const m of ttlContent.matchAll(/oc:hasReferenceFile\s+\[?\s*[\s\S]*?oc:filePath\s+"([^"]+)"[\s\S]*?oc:purpose\s+"([^"]+)"/g)) {
    const refId = `ref:${m[1]}`;
    const refNode = addNode(refId, m[1], 'referenceFile');
    if (refNode) refNode.description = m[2];
    edges.push({ source: rootId, target: refId });
  }

  // Executable scripts
  for (const m of ttlContent.matchAll(/oc:hasExecutableScript\s+\[?\s*[\s\S]*?oc:filePath\s+"([^"]+)"[\s\S]*?oc:scriptExecutor\s+"([^"]+)"/g)) {
    const scrId = `script:${m[1]}`;
    const scrNode = addNode(scrId, m[1], 'script');
    if (scrNode) scrNode.description = `Executor: ${m[2]}`;
    edges.push({ source: rootId, target: scrId });
  }

  // Workflows
  for (const m of ttlContent.matchAll(/oc:hasWorkflow\s+\[?\s*[\s\S]*?oc:workflowName\s+"([^"]+)"/g)) {
    const wfId = `workflow:${m[1]}`;
    addNode(wfId, m[1], 'workflow');
    edges.push({ source: rootId, target: wfId });
  }

  // Examples
  for (const m of ttlContent.matchAll(/oc:hasExample\s+\[?\s*[\s\S]*?oc:exampleName\s+"([^"]+)"/g)) {
    const exId = `example:${m[1]}`;
    addNode(exId, m[1], 'example');
    edges.push({ source: rootId, target: exId });
  }

  // Execution payloads
  for (const m of ttlContent.matchAll(/oc:hasPayload\s+\[?\s*[\s\S]*?oc:executor\s+"([^"]+)"/g)) {
    const payId = `payload:${m[1]}`;
    const payNode = addNode(payId, `Payload (${m[1]})`, 'payload');
    if (payNode) payNode.description = `Executor: ${m[1]}`;
    edges.push({ source: rootId, target: payId });
  }

  return { nodes, edges };
}
