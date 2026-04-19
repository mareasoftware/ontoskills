import type { GraphNode, GraphEdge } from './types';

function escRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// Map category names to readable labels
const CATEGORY_NAMES: Record<string, string> = {
  dependency: 'Depends on',
  extends: 'Extends',
  contradicts: 'Contradicts',
  yield: 'Yields',
  require: 'Requires',
  failure: 'Failure',
  intent: 'Intent',
  tool: 'Tool',
  constraint: 'Constraint',
  requirement: 'Requirement',
  referenceFile: 'Reference',
  script: 'Script',
  workflow: 'Workflow',
  example: 'Example',
  payload: 'Payload',
};

function categoryLabel(cat: string): string {
  return CATEGORY_NAMES[cat] || cat.replace(/([A-Z])/g, ' $1').trim();
}

export function parseTtlKnowledgeMap(ttlContent: string, skillId: string) {
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];
  const rootId = `skill:${skillId}`;
  const seen = new Set<string>();

  nodes.push({ id: rootId, label: skillId, category: 'skill', qualifiedId: skillId, isHighlighted: true });
  seen.add(rootId);

  const addNode = (id: string, label: string, category: string, value?: string): GraphNode | null => {
    if (seen.has(id)) return null;
    seen.add(id);
    const node: GraphNode = { id, label, category, qualifiedId: id, isHighlighted: false };
    if (value) node.value = value;
    nodes.push(node);
    return node;
  };

  // Skill dependencies
  for (const m of ttlContent.matchAll(/oc:dependsOnSkill\s+oc:skill_([^\s;,]+)/g)) {
    const depId = `dep:${m[1]}`;
    const depName = m[1].replace(/_/g, '-');
    const depNode = addNode(depId, categoryLabel('dependency'), 'dependency', depName);
    if (depNode) depNode.description = depName;
    edges.push({ source: rootId, target: depId });
  }

  // Skill inheritance
  for (const m of ttlContent.matchAll(/oc:extends\s+oc:skill_([^\s;,]+)/g)) {
    const extId = `extends:${m[1]}`;
    const extName = m[1].replace(/_/g, '-');
    const extNode = addNode(extId, categoryLabel('extends'), 'extends', extName);
    if (extNode) extNode.description = extName;
    edges.push({ source: rootId, target: extId });
  }

  // Skill mutual exclusion
  for (const m of ttlContent.matchAll(/oc:contradicts\s+oc:skill_([^\s;,]+)/g)) {
    const conId = `contradicts:${m[1]}`;
    const conName = m[1].replace(/_/g, '-');
    const conNode = addNode(conId, categoryLabel('contradicts'), 'contradicts', conName);
    if (conNode) conNode.description = conName;
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
    const knLabel = categoryLabel(knType);
    const rationaleMatch = ttlContent.match(new RegExp(`oc:${escRegex(knId)}[\\s\\S]*?oc:hasRationale\\s+"([^"]+)"`));
    const description = [fullContext, rationaleMatch?.[1]].filter(Boolean).join(' — ') || undefined;
    const knNode = addNode(knId, knLabel, knType);
    if (knNode) {
      if (fullContext) knNode.value = fullContext;
      knNode.description = description;
    }
    edges.push({ source: rootId, target: knId });
  }

  // States — yields and requires
  for (const m of ttlContent.matchAll(/oc:(yieldsState|requiresState)\s+oc:(\w+)/g)) {
    const stateId = `state:${m[2]}`;
    const stateName = m[2].replace(/([A-Z])/g, ' $1').trim();
    const cat = m[1] === 'yieldsState' ? 'yield' : 'require';
    const stateNode = addNode(stateId, categoryLabel(cat), cat, stateName);
    if (stateNode) stateNode.description = m[1] === 'yieldsState' ? `Produced: ${stateName}` : `Required: ${stateName}`;
    edges.push({ source: rootId, target: stateId });
  }

  // Failure states
  for (const m of ttlContent.matchAll(/oc:handlesFailure\s+oc:(\w+)/g)) {
    const failId = `fail:${m[1]}`;
    const failName = m[1].replace(/([A-Z])/g, ' $1').trim();
    const failNode = addNode(failId, categoryLabel('failure'), 'failure', failName);
    if (failNode) failNode.description = failName;
    edges.push({ source: rootId, target: failId });
  }

  // Intents
  for (const m of ttlContent.matchAll(/oc:resolvesIntent\s+"([^"]+)"/g)) {
    const intentId = `intent:${m[1]}`;
    const intNode = addNode(intentId, categoryLabel('intent'), 'intent', m[1]);
    if (intNode) intNode.description = m[1];
    edges.push({ source: rootId, target: intentId });
  }

  // Allowed tools
  for (const m of ttlContent.matchAll(/oc:hasAllowedTool\s+"([^"]+)"/g)) {
    const toolId = `tool:${m[1]}`;
    const toolNode = addNode(toolId, categoryLabel('tool'), 'tool', m[1]);
    if (toolNode) toolNode.description = m[1];
    edges.push({ source: rootId, target: toolId });
  }

  // Constraints
  for (const m of ttlContent.matchAll(/oc:hasConstraint\s+"([^"]+)"/g)) {
    const cId = `constraint:${m[1]}`;
    const cNode = addNode(cId, categoryLabel('constraint'), 'constraint', m[1]);
    if (cNode) cNode.description = m[1];
    edges.push({ source: rootId, target: cId });
  }

  // Requirements
  for (const m of ttlContent.matchAll(/oc:hasRequirement\s+\[?\s*[\s\S]*?oc:requirementValue\s+"([^"]+)"[\s\S]*?oc:isOptional\s+"?(true|false)"?/g)) {
    const reqId = `requirement:${m[1]}`;
    const reqNode = addNode(reqId, categoryLabel('requirement'), 'requirement', m[1]);
    if (reqNode) reqNode.description = `${m[2] === 'true' ? 'Optional' : 'Required'}: ${m[1]}`;
    edges.push({ source: rootId, target: reqId });
  }

  // Reference files
  for (const m of ttlContent.matchAll(/oc:hasReferenceFile\s+\[?\s*[\s\S]*?oc:filePath\s+"([^"]+)"[\s\S]*?oc:purpose\s+"([^"]+)"/g)) {
    const refId = `ref:${m[1]}`;
    const refNode = addNode(refId, categoryLabel('referenceFile'), 'referenceFile', m[1]);
    if (refNode) refNode.description = `${m[1]} — ${m[2]}`;
    edges.push({ source: rootId, target: refId });
  }

  // Executable scripts
  for (const m of ttlContent.matchAll(/oc:hasExecutableScript\s+\[?\s*[\s\S]*?oc:filePath\s+"([^"]+)"[\s\S]*?oc:scriptExecutor\s+"([^"]+)"/g)) {
    const scrId = `script:${m[1]}`;
    const scrNode = addNode(scrId, categoryLabel('script'), 'script', m[1]);
    if (scrNode) scrNode.description = `${m[1]} — Executor: ${m[2]}`;
    edges.push({ source: rootId, target: scrId });
  }

  // Workflows
  for (const m of ttlContent.matchAll(/oc:hasWorkflow\s+\[?\s*[\s\S]*?oc:workflowName\s+"([^"]+)"/g)) {
    const wfId = `workflow:${m[1]}`;
    const wfNode = addNode(wfId, categoryLabel('workflow'), 'workflow', m[1]);
    if (wfNode) wfNode.description = m[1];
    edges.push({ source: rootId, target: wfId });
  }

  // Examples
  for (const m of ttlContent.matchAll(/oc:hasExample\s+\[?\s*[\s\S]*?oc:exampleName\s+"([^"]+)"/g)) {
    const exId = `example:${m[1]}`;
    const exNode = addNode(exId, categoryLabel('example'), 'example', m[1]);
    if (exNode) exNode.description = m[1];
    edges.push({ source: rootId, target: exId });
  }

  // Execution payloads
  for (const m of ttlContent.matchAll(/oc:hasPayload\s+\[?\s*[\s\S]*?oc:executor\s+"([^"]+)"/g)) {
    const payId = `payload:${m[1]}`;
    const payNode = addNode(payId, categoryLabel('payload'), 'payload', m[1]);
    if (payNode) payNode.description = `Executor: ${m[1]}`;
    edges.push({ source: rootId, target: payId });
  }

  return { nodes, edges };
}
