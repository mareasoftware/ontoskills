export interface Skill {
  packageId: string;
  skillId: string;
  qualifiedId: string;
  description: string;
  aliases: string[];
  trustTier: string;
  installCommand: string;
  author: string;
  category: string;
  intents: string[];
  dependsOn: string[];
  version: string;
  modules: string[];
}

export interface GraphNode {
  id: string;
  label: string;
  category: string;
  qualifiedId: string;
  isHighlighted: boolean;
  description?: string;
  value?: string;
  isCluster?: boolean;
  clusterNodes?: GraphNode[];
  count?: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  directed?: boolean;
}

export interface PackageManifest {
  package_id: string;
  description?: string;
  version?: string;
  modules?: string[];
  skills?: any[];
}

export type ViewMode = 'store' | 'author' | 'package' | 'skill';

export type GraphLevel =
  | { type: 'author'; authorId: string }
  | { type: 'package'; authorId: string; pkgId: string }
  | { type: 'skill'; pkgId: string; skillId: string; mode: 'files' | 'knowledge' };

export type Translations = {
  searchPlaceholder: string;
  storeLabel: string;
  loading: string;
  connecting: string;
  noDescription: string;
  official: string;
  verified: string;
  community: string;
  install: string;
  copyToClipboard: string;
  unableToLoad: string;
  showingResults: string;
  allSkills: string;
  noMatch: string;
  trySearch: string;
  skill_one: string;
  skill_other: string;
  retry: string;
  allAuthors: string;
  allCategories: string;
  allTiers: string;
  author: string;
  category: string;
  trustTier: string;
  sort: string;
  sortAZ: string;
  sortZA: string;
  intents: string;
  intent_one: string;
  intent_other: string;
  dependencies: string;
  dependency_one: string;
  dependency_other: string;
  fileTree: string;
  knowledgeGraph: string;
  skills: string;
  packages: string;
  package_one: string;
  package_other: string;
  totalSkills: string;
  files_other: string;
  file_one: string;
  file_other: string;
  aliases: string;
  alias_one: string;
  alias_other: string;
  nodes: string;
  node_one: string;
  node_other: string;
  edges: string;
  edge_one: string;
  edge_other: string;
  getStarted: string;
  step1Title: string;
  step1Desc: string;
  step2Title: string;
  step2Desc: string;
  step3Title: string;
  step3Desc: string;
  setupMcpCommand: string;
  setupSkillCommand: string;
  setupDocs: string;
  noDeps: string;
  copied: string;
  loadMore: string;
  remaining: string;
  more: string;
  fileGraph: string;
  knowledgeMap: string;
  loadingGraph: string;
  loading3d: string;
  graphError: string;
  legend: string;
  controls: string;
  value: string;
  properties: string;
  type: string;
  id: string;
  state: string;
  connectedTo: string;
  noConnections: string;
  openKnowledgeMap: string;
  viewSkill: string;
  clickToExplore: string;
  clusterInstances: string;
  viewRaw: string;
  officialStore: string;
  exploreGraph: string;
  backToGraph: string;
  authorGraph: string;
  packageGraph: string;
  skillGraph: string;
  ctrlZoom: string;
  ctrlOrbit: string;
  ctrlPan: string;
  ctrlDetails: string;
  ctrlClose: string;
};
