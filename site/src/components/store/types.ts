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
}

export interface GraphEdge {
  source: string;
  target: string;
}

export interface PackageManifest {
  package_id: string;
  description?: string;
  version?: string;
  modules?: string[];
  skills?: any[];
}

export type ViewMode = 'store' | 'author' | 'package' | 'skill';

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
  dependencies: string;
  fileTree: string;
  knowledgeGraph: string;
  skills: string;
  packages: string;
  totalSkills: string;
  files_other: string;
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
  viewPackageGraph: string;
  backToSkillGraph: string;
  copied: string;
  loadMore: string;
  remaining: string;
  aliases: string;
  more: string;
  fileGraph: string;
  knowledgeMap: string;
  openGraph: string;
  loadingGraph: string;
  graphError: string;
  legend: string;
  nodes: string;
  edges: string;
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
  more: string;
};
