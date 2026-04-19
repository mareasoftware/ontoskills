/**
 * Category color palette for 3D graph nodes.
 *
 * Design rules:
 * - Colors are perceptually spaced (~30° hue separation) for maximum distinction
 * - Saturation kept at 70–85% for vibrancy on dark backgrounds
 * - Lightness kept at 60–70% for readability without eye strain
 * - File categories (main/prompt/test/module) use warm tones
 * - Semantic categories (anti-pattern/recovery/failure) use alert tones
 * - State categories (yield/require/tool) use cool/muted tones
 */

// 16 hues spaced ~22.5° apart, high saturation, good lightness for dark bg
const HUE_PALETTE = [
  '#e05252', // 0°   red
  '#e07a3a', // 25°  burnt orange
  '#dba32c', // 45°  gold
  '#a8c034', // 75°  yellow-green
  '#52bf5a', // 130° green
  '#38c490', // 160° teal-green
  '#36c5b8', // 175° teal
  '#3bb8c9', // 195° cyan
  '#3da0d9', // 210° blue
  '#5482d6', // 225° royal blue
  '#7b6ad8', // 255° indigo
  '#9d5cd5', // 275° purple
  '#c054c9', // 295° magenta
  '#d64f9f', // 320° hot pink
  '#d84d74', // 340° rose
  '#d85a5e', // 355° coral
];

export const CATEGORY_COLORS: Record<string, string> = {
  // Skill root
  skill:          '#e0e0e0', // bright neutral white — root node stands out

  // Graph-level entities
  author:          '#52c7e8', // cyan — brand
  package:         '#a78bfa', // purple — package clusters

  // File categories — warm family
  main:           '#dba32c', // gold
  prompt:         '#e07a3a', // burnt orange
  test:           '#52bf5a', // green
  module:         '#c054c9', // magenta

  // Skill relationships
  dependency:     '#3da0d9', // blue
  extends:        '#9d5cd5', // purple — inheritance
  contradicts:    '#e05252', // red — conflict

  // Skill properties
  intent:         '#dba32c', // gold — matches intent UI
  constraint:     '#e07a3a', // burnt orange — limits
  tool:           '#e0e0e0', // neutral
  requirement:    '#d84d74', // rose — prerequisites

  // Composite objects
  payload:        '#36c5b8', // teal — execution
  referenceFile:  '#5482d6', // royal blue — documentation
  script:         '#a8c034', // yellow-green — executable
  workflow:       '#c054c9', // magenta — process
  example:        '#52bf5a', // green — demonstration

  // Semantic — alert family
  AntiPattern:    '#e05252', // red
  RecoveryTactic: '#36c5b8', // teal
  failure:        '#d84d74', // rose

  // State categories — cool/muted family
  yield:          '#38c490', // teal-green
  require:        '#7b6ad8', // indigo

  // Domain categories
  productivity:   '#5482d6', // royal blue
  development:    '#a8c034', // yellow-green
};

export const PALETTE_FALLBACK = HUE_PALETTE;

import { hashStr } from '../helpers';

export function getNodeColor(category: string, isHighlighted: boolean): string {
  if (isHighlighted) return '#52c7e8';
  if (CATEGORY_COLORS[category]) return CATEGORY_COLORS[category];
  return PALETTE_FALLBACK[hashStr(category) % PALETTE_FALLBACK.length];
}

export function getConnectedNodes(node: import('../types').GraphNode, edges: import('../types').GraphEdge[], allNodes: import('../types').GraphNode[]): import('../types').GraphNode[] {
  const ids = new Set<string>();
  for (const e of edges) {
    if (e.source === node.id) ids.add(e.target);
    if (e.target === node.id) ids.add(e.source);
  }
  return allNodes.filter(n => ids.has(n.id));
}

export const CATEGORY_LABELS: Record<string, [string, string]> = {
  skill:           ['Skill',          CATEGORY_COLORS.skill],
  author:          ['Author',   CATEGORY_COLORS.author],
  package:         ['Package',  CATEGORY_COLORS.package],
  main:            ['ontoskill.ttl',  CATEGORY_COLORS.main],
  prompt:          ['Prompt',         CATEGORY_COLORS.prompt],
  test:            ['Test',           CATEGORY_COLORS.test],
  module:          ['Module',         CATEGORY_COLORS.module],
  dependency:      ['Depends on',     CATEGORY_COLORS.dependency],
  extends:         ['Extends',        CATEGORY_COLORS.extends],
  contradicts:     ['Contradicts',    CATEGORY_COLORS.contradicts],
  intent:          ['Intent',         CATEGORY_COLORS.intent],
  constraint:      ['Constraint',     CATEGORY_COLORS.constraint],
  tool:            ['Tool',           CATEGORY_COLORS.tool],
  requirement:     ['Requirement',    CATEGORY_COLORS.requirement],
  payload:         ['Payload',        CATEGORY_COLORS.payload],
  referenceFile:   ['Reference',      CATEGORY_COLORS.referenceFile],
  script:          ['Script',         CATEGORY_COLORS.script],
  workflow:        ['Workflow',       CATEGORY_COLORS.workflow],
  example:         ['Example',        CATEGORY_COLORS.example],
  AntiPattern:     ['Anti-pattern',   CATEGORY_COLORS.AntiPattern],
  RecoveryTactic:  ['Recovery',       CATEGORY_COLORS.RecoveryTactic],
  failure:         ['Failure',        CATEGORY_COLORS.failure],
  yield:           ['Yields',         CATEGORY_COLORS.yield],
  require:         ['Requires',       CATEGORY_COLORS.require],
  productivity:    ['Productivity',   CATEGORY_COLORS.productivity],
  development:     ['Development',    CATEGORY_COLORS.development],
};

export const CATEGORY_DESCRIPTIONS: Record<string, string> = {
  skill: 'The root skill definition',
  author: 'The skill author',
  package: 'A collection of related skills',
  main: 'Primary ontology file',
  prompt: 'Prompt template definitions',
  test: 'Test specifications',
  module: 'Additional ontology modules',
  dependency: 'Required skill dependencies',
  extends: 'Skill inheritance (parent skill)',
  contradicts: 'Mutually exclusive skill',
  intent: 'User intents resolved by this skill',
  constraint: 'Execution constraints or limitations',
  tool: 'Allowed tool integrations',
  requirement: 'Runtime requirements',
  payload: 'Execution payload (code/script)',
  referenceFile: 'Reference file for progressive disclosure',
  script: 'Executable script',
  workflow: 'Multi-step workflow',
  example: 'Input/output example',
  AntiPattern: 'Common mistakes to avoid',
  RecoveryTactic: 'Error recovery strategies',
  failure: 'Known failure modes',
  yield: 'States produced after execution',
  require: 'States required before execution',
};
