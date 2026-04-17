import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { OrbitControls, Line, Html } from '@react-three/drei';
import * as THREE from 'three';

// ─── Types ────────────────────────────────────────────────

interface Skill {
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

interface GraphNode {
  id: string;
  label: string;
  category: string;
  qualifiedId: string;
  isHighlighted: boolean;
  description?: string;
}

interface GraphEdge {
  source: string;
  target: string;
}

type ViewMode = 'store' | 'author' | 'package' | 'skill';

// ─── i18n ─────────────────────────────────────────────────

const translations = {
  en: {
    searchPlaceholder: 'Search ontoskills, intents, or descriptions...',
    storeLabel: 'OntoStore',
    loading: 'Loading store…',
    connecting: 'Connecting to the official store…',
    noDescription: 'No description available.',
    official: 'official',
    verified: 'verified',
    community: 'community',
    install: 'Install',
    copyToClipboard: 'Copy to clipboard',
    unableToLoad: 'Unable to load store data.',
    showingResults: 'Showing results for',
    allSkills: 'All published ontoskills from the official registry.',
    noMatch: 'No matching ontoskills found',
    trySearch: 'Try searching for: hello, xlsx, docx, or office',
    skill_one: 'ontoskill',
    skill_other: 'ontoskills',
    retry: 'Retry',
    allAuthors: 'All authors',
    allCategories: 'All categories',
    allTiers: 'All tiers',
    author: 'Author',
    category: 'Category',
    trustTier: 'Trust',
    sort: 'Sort',
    sortAZ: 'A → Z',
    sortZA: 'Z → A',
    intents: 'Intents',
    dependencies: 'Dependencies',
    fileTree: 'Files',
    knowledgeGraph: 'Knowledge Graph',
    skills: 'OntoSkills',
    packages: 'Packages',
    totalSkills: 'total ontoskills',
    files_other: 'files',
    getStarted: 'Get Started',
    step1Title: '1. Install the MCP server',
    step1Desc: 'Add OntoSkills to your AI assistant via the MCP protocol.',
    step2Title: '2. Install your first ontoskill',
    step2Desc: 'Browse the store, pick a skill, and install it with one command.',
    step3Title: '3. Start using it',
    step3Desc: 'Your AI assistant can now resolve intents to the skills you installed.',
    setupMcpCommand: 'npx ontoskills install mcp',
    setupSkillCommand: 'npx ontoskills install obra/superpowers',
    setupDocs: 'Read the docs',
    noDeps: 'No dependencies',
    viewPackageGraph: 'View package graph',
    backToSkillGraph: '← Back to skill graph',
    copied: 'Copied!',
    loadMore: 'Load more',
    remaining: 'remaining',
    aliases: 'Aliases',
    fileGraph: 'File Graph',
    knowledgeMap: 'Knowledge Map',
    openGraph: 'Open 3D Graph',
    loadingGraph: 'Parsing TTL files…',
    graphError: 'Failed to load graph data.',
    legend: 'Legend',
    nodes: 'nodes',
    edges: 'edges',
    controls: 'Controls',
  },
  zh: {
    searchPlaceholder: '按本体技能、意图或描述搜索...',
    storeLabel: 'OntoStore',
    loading: '加载商店中…',
    connecting: '正在连接官方商店…',
    noDescription: '暂无描述。',
    official: '官方',
    verified: '已验证',
    community: '社区',
    install: '安装',
    copyToClipboard: '复制到剪贴板',
    unableToLoad: '无法加载商店数据。',
    showingResults: '显示搜索结果',
    allSkills: '来自官方注册表的所有已发布本体技能。',
    noMatch: '未找到匹配的本体技能',
    trySearch: '尝试搜索: hello, xlsx, docx, 或 office',
    skill_one: '个本体技能',
    skill_other: '个本体技能',
    retry: '重试',
    allAuthors: '所有作者',
    allCategories: '所有类别',
    allTiers: '所有层级',
    author: '作者',
    category: '类别',
    trustTier: '信任',
    sort: '排序',
    sortAZ: 'A → Z',
    sortZA: 'Z → A',
    intents: '意图',
    dependencies: '依赖',
    fileTree: '文件',
    knowledgeGraph: '知识图谱',
    skills: '本体技能',
    packages: '包',
    totalSkills: '个本体技能',
    files_other: '个文件',
    getStarted: '快速开始',
    step1Title: '1. 安装 MCP 服务器',
    step1Desc: '通过 MCP 协议将 OntoSkills 添加到你的 AI 助手。',
    step2Title: '2. 安装你的第一个本体技能',
    step2Desc: '浏览商店，选择一个技能，一行命令安装。',
    step3Title: '3. 开始使用',
    step3Desc: '你的 AI 助手现在可以根据意图调用已安装的技能。',
    setupMcpCommand: 'npx ontoskills install mcp',
    setupSkillCommand: 'npx ontoskills install obra/superpowers',
    setupDocs: '阅读文档',
    noDeps: '无依赖',
    viewPackageGraph: '查看包图谱',
    backToSkillGraph: '← 返回技能图谱',
    copied: '已复制!',
    loadMore: '加载更多',
    remaining: '剩余',
    aliases: '别名',
    fileGraph: '文件图谱',
    knowledgeMap: '知识图谱',
    openGraph: '打开 3D 图谱',
    loadingGraph: '正在解析 TTL 文件…',
    graphError: '加载图谱数据失败。',
    legend: '图例',
    nodes: '节点',
    edges: '边',
    controls: '快捷键',
  },
};

// ─── Helpers ──────────────────────────────────────────────

const STORE_INDEX_URL = 'https://raw.githubusercontent.com/mareasw/ontostore/main/index.json';

function normSkill(pkg: any, skill: any): Skill {
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

function buildGraphData(skillList: Skill[], highlightId: string | null = null) {
  const idSet = new Set(skillList.map(s => s.skillId));
  const nodes: GraphNode[] = skillList.map(s => ({
    id: s.skillId,
    label: s.skillId,
    category: s.category,
    qualifiedId: s.qualifiedId,
    isHighlighted: s.skillId === highlightId,
  }));
  const edges: GraphEdge[] = [];
  for (const s of skillList) {
    for (const d of s.dependsOn) {
      if (d !== s.skillId && idSet.has(d)) edges.push({ source: s.skillId, target: d });
    }
  }
  return { nodes, edges };
}

function packageHasDeps(skillList: Skill[]) {
  const idSet = new Set(skillList.map(s => s.skillId));
  return skillList.some(s => s.dependsOn.some(d => idSet.has(d)));
}

const TTL_BASE = STORE_INDEX_URL.replace('index.json', 'packages/');

function buildFileGraphData(modules: string[], skillId: string) {
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

function parseTtlKnowledgeMap(ttlContent: string, skillId: string) {
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

  // dependsOnSkill
  for (const m of ttlContent.matchAll(/oc:dependsOnSkill\s+oc:skill_([^\s;,]+)/g)) {
    const depId = `dep:${m[1]}`;
    addNode(depId, m[1].replace(/_/g, '-'), 'dependency');
    edges.push({ source: rootId, target: depId });
  }

  // Knowledge nodes — find all kn_ references from impartsKnowledge blocks (multi-line)
  const knRefs = new Set<string>();
  for (const m of ttlContent.matchAll(/oc:(kn_[a-f0-9]+)/g)) {
    knRefs.add(m[1]);
  }
  for (const knId of knRefs) {
    // Find the type declaration for this knowledge node
    const typeMatch = ttlContent.match(new RegExp(`oc:${knId}\\s+a\\s+oc:KnowledgeNode(?:,\\s*oc:(\\w+))?`));
    if (!typeMatch) continue; // Skip if not a KnowledgeNode declaration
    const knType = typeMatch[1] || 'KnowledgeNode';
    // Extract full context for label and description
    const ctxMatch = ttlContent.match(new RegExp(`oc:${knId}[\\s\\S]*?oc:appliesToContext\\s+"([^"]+)"`));
    const fullContext = ctxMatch ? ctxMatch[1] : '';
    const label = fullContext.length > 40 ? fullContext.slice(0, 40) + '…' : fullContext || knType.replace(/([A-Z])/g, ' $1').trim();
    // Extract appliesToCondition if present
    const condMatch = ttlContent.match(new RegExp(`oc:${knId}[\\s\\S]*?oc:appliesToCondition\\s+"([^"]+)"`));
    const description = [fullContext, condMatch?.[1]].filter(Boolean).join(' — ') || undefined;
    const knNode = addNode(knId, label, knType);
    if (knNode) knNode.description = description;
    edges.push({ source: rootId, target: knId });
  }

  // States — multi-line support
  for (const m of ttlContent.matchAll(/oc:(yieldsState|requiresState)\s+oc:(\w+)/g)) {
    const stateId = `state:${m[2]}`;
    const stateLabel = m[2].replace(/([A-Z])/g, ' $1').trim();
    const stateNode = addNode(stateId, stateLabel, m[1] === 'yieldsState' ? 'yield' : 'require');
    if (stateNode) stateNode.description = m[1] === 'yieldsState' ? `Produced after ${stateLabel.toLowerCase()}` : `Required before execution`;
    edges.push({ source: rootId, target: stateId });
  }
  // Also capture states on continuation lines
  for (const m of ttlContent.matchAll(/^\s+oc:(\w+)\s*[,;]$/gm)) {
    const name = m[1];
    if (/^[A-Z]/.test(name)) {
      const stateId = `state:${name}`;
      if (!seen.has(stateId)) {
        addNode(stateId, name.replace(/([A-Z])/g, ' $1').trim(), 'yield');
        edges.push({ source: rootId, target: stateId });
      }
    }
  }

  // Failure handlers
  for (const m of ttlContent.matchAll(/oc:handlesFailure\s+oc:(\w+)/g)) {
    const failId = `fail:${m[1]}`;
    addNode(failId, m[1].replace(/([A-Z])/g, ' $1').trim(), 'failure');
    edges.push({ source: rootId, target: failId });
  }

  // Allowed tools
  for (const m of ttlContent.matchAll(/oc:hasAllowedTool\s+"(\w+)"/g)) {
    const toolId = `tool:${m[1]}`;
    addNode(toolId, m[1], 'tool');
    edges.push({ source: rootId, target: toolId });
  }

  return { nodes, edges };
}

function layoutForce3D(nodes: GraphNode[], edges: GraphEdge[]) {
  const positions: Record<string, { x: number; y: number; z: number }> = {};
  const n = nodes.length;
  if (!n) return positions;
  // Distribute nodes on a sphere surface
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
  // Gentle force simulation — bounded to avoid NaN
  for (let iter = 0; iter < 120; iter++) {
    const cooling = 0.1 * (1 - iter / 120);
    // Repulsion between all pairs
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
    // Attraction along edges
    for (const e of edges) {
      const s = positions[e.source], t = positions[e.target];
      if (!s || !t) continue;
      const dx = t.x - s.x, dy = t.y - s.y, dz = t.z - s.z;
      const dist = Math.sqrt(Math.max(dx * dx + dy * dy + dz * dz, 0.01));
      const f = dist * 0.05 * cooling;
      s.x += (dx / dist) * f; s.y += (dy / dist) * f; s.z += (dz / dist) * f;
      t.x -= (dx / dist) * f; t.y -= (dy / dist) * f; t.z -= (dz / dist) * f;
    }
    // Clamp to sphere
    for (const node of nodes) {
      const p = positions[node.id];
      const d = Math.sqrt(p.x * p.x + p.y * p.y + p.z * p.z);
      if (d > 25) { p.x *= 25 / d; p.y *= 25 / d; p.z *= 25 / d; }
    }
  }
  // Final NaN guard
  for (const node of nodes) {
    const p = positions[node.id];
    if (!isFinite(p.x)) p.x = 0;
    if (!isFinite(p.y)) p.y = 0;
    if (!isFinite(p.z)) p.z = 0;
  }
  return positions;
}

// ─── 3D Graph Components ──────────────────────────────────

const CATEGORY_COLORS: Record<string, string> = {
  skill:         '#52c7e8',
  main:          '#818cf8',
  prompt:        '#4ade80',
  test:          '#fbbf24',
  module:        '#f472b6',
  dependency:    '#fb923c',
  AntiPattern:   '#ef4444',
  RecoveryTactic:'#e879f9',
  failure:       '#a16207',
  yield:         '#2dd4bf',
  require:       '#a78bfa',
  tool:          '#facc15',
  productivity:  '#38bdf8',
  development:   '#67e8f9',
};

const PALETTE_FALLBACK = ['#f97316','#ec4899','#06b6d4','#84cc16','#d946ef','#14b8a6','#f43f5e','#0ea5e9','#eab308','#7c3aed','#10b981','#e11d48','#6366f1','#f59e0b','#22d3ee','#be123c'];

function hashStr(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

function getNodeColor(category: string, isHighlighted: boolean): string {
  if (isHighlighted) return '#52c7e8';
  if (CATEGORY_COLORS[category]) return CATEGORY_COLORS[category];
  return PALETTE_FALLBACK[hashStr(category) % PALETTE_FALLBACK.length];
}

function getConnectedNodes(node: GraphNode, edges: GraphEdge[], allNodes: GraphNode[]): GraphNode[] {
  const ids = new Set<string>();
  for (const e of edges) {
    if (e.source === node.id) ids.add(e.target);
    if (e.target === node.id) ids.add(e.source);
  }
  return allNodes.filter(n => ids.has(n.id));
}

function GraphNodeSphere({ node, position, onClick, dimmed = false }: {
  node: GraphNode;
  position: [number, number, number];
  onClick: (node: GraphNode) => void;
  dimmed?: boolean;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const [hovered, setHovered] = useState(false);
  const color = getNodeColor(node.category, node.isHighlighted);
  const radius = node.isHighlighted ? 1.4 : 0.9;
  const isExplorable = ['main', 'prompt', 'test', 'module'].includes(node.category) && node.qualifiedId.endsWith('.ttl');
  const categoryLabel = CATEGORY_LABELS[node.category]?.[0] || node.category;

  const labelStyle: React.CSSProperties = {
    fontSize: '12px',
    fontWeight: 600,
    fontFamily: "'Inter Variable', 'Inter', system-ui, sans-serif",
    color: dimmed ? 'rgba(224,224,224,0.12)' : '#e0e0e0',
    background: 'rgba(9, 9, 9, 0.75)',
    padding: '3px 8px',
    borderRadius: '4px',
    border: '1px solid rgba(255,255,255,0.06)',
    backdropFilter: 'blur(4px)',
    WebkitBackdropFilter: 'blur(4px)',
    whiteSpace: 'nowrap' as const,
    userSelect: 'none',
    textShadow: '0 1px 2px rgba(0,0,0,0.5)',
    maxWidth: '180px',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    transition: 'opacity 0.3s',
    opacity: dimmed ? 0.12 : 1,
  };

  const tooltipStyle: React.CSSProperties = {
    background: 'rgba(9, 9, 9, 0.95)',
    backdropFilter: 'blur(8px)',
    WebkitBackdropFilter: 'blur(8px)',
    border: '1px solid rgba(255,255,255,0.1)',
    borderRadius: '8px',
    padding: '8px 12px',
    whiteSpace: 'nowrap' as const,
    pointerEvents: 'none',
  };

  return (
    <group position={position}>
      {node.isHighlighted && !dimmed && (
        <mesh>
          <sphereGeometry args={[radius * 2.5, 32, 32]} />
          <meshBasicMaterial color={color} transparent opacity={0.08} />
        </mesh>
      )}
      <mesh
        ref={meshRef}
        onClick={(e) => { e.stopPropagation(); onClick(node); }}
        onPointerOver={(e) => { e.stopPropagation(); setHovered(true); document.body.style.cursor = 'pointer'; }}
        onPointerOut={() => { setHovered(false); document.body.style.cursor = 'default'; }}
      >
        <sphereGeometry args={[radius, 32, 32]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={hovered && !dimmed ? 0.6 : node.isHighlighted && !dimmed ? 0.4 : 0.15}
          roughness={0.3}
          metalness={0.2}
          transparent
          opacity={dimmed ? 0.12 : 0.9}
        />
      </mesh>
      {/* Label below node */}
      <Html
        position={[0, -(radius + 0.5), 0]}
        center
        style={{ pointerEvents: 'none' }}
        zIndexRange={[50, 0]}
      >
        <div style={labelStyle}>{node.label}</div>
      </Html>
      {/* Hover tooltip above node — clickable to select node */}
      {hovered && !dimmed && (
        <Html position={[0, radius + 1.2, 0]} center zIndexRange={[100, 0]}>
          <div
            onClick={() => onClick(node)}
            style={{ ...tooltipStyle, pointerEvents: 'auto', cursor: 'pointer' }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
              <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: color, display: 'inline-block' }} />
              <span style={{ fontSize: '13px', fontWeight: 600, color: '#f5f5f5' }}>{node.label}</span>
            </div>
            <span style={{ fontSize: '10px', color: '#8a8a8a', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
              {categoryLabel}
            </span>
            {isExplorable && (
              <div style={{ fontSize: '10px', color: '#52c7e8', marginTop: '6px' }}>Click to explore →</div>
            )}
          </div>
        </Html>
      )}
    </group>
  );
}

function GraphEdgeLine({ start, end, sourceColor, targetColor }: { start: [number, number, number]; end: [number, number, number]; sourceColor?: string; targetColor?: string }) {
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

function AutoRotate() {
  const { camera } = useThree();
  useFrame(() => {
    camera.position.applyAxisAngle(new THREE.Vector3(0, 1, 0), 0.002);
    camera.lookAt(0, 0, 0);
  });
  return null;
}

function CameraFocus({ target, active }: { target: [number, number, number]; active: boolean }) {
  const { camera } = useThree();
  const targetVec = useRef(new THREE.Vector3(...target));
  targetVec.current.set(...target);
  useFrame(() => {
    if (!active) return;
    const desired = new THREE.Vector3(target[0] + 14, target[1] + 10, target[2] + 14);
    camera.position.lerp(desired, 0.04);
    camera.lookAt(targetVec.current);
  });
  return null;
}

function BackgroundParticles() {
  const count = 150;
  const positions = useMemo(() => {
    const arr = new Float32Array(count * 3);
    for (let i = 0; i < count * 3; i++) arr[i] = (Math.random() - 0.5) * 120;
    return arr;
  }, []);
  return (
    <points>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" count={count} array={positions} itemSize={3} />
      </bufferGeometry>
      <pointsMaterial color="#52c7e8" size={0.08} transparent opacity={0.2} blending={THREE.AdditiveBlending} depthWrite={false} />
    </points>
  );
}

function Scene({ nodes, edges, onNodeClick, autoRotate = true, highlightCategory, focusNodeId }: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  onNodeClick: (node: GraphNode) => void;
  autoRotate?: boolean;
  highlightCategory?: string | null;
  focusNodeId?: string | null;
}) {
  const positions = useMemo(() => layoutForce3D(nodes, edges), [nodes, edges]);
  const focusNode = focusNodeId ? nodes.find(n => n.id === focusNodeId) : null;
  const focusPos = focusNode ? positions[focusNode.id] : null;

  return (
    <>
      <ambientLight intensity={0.5} />
      <pointLight position={[20, 20, 20]} intensity={1.5} color="#52c7e8" />
      <pointLight position={[-20, -10, 15]} intensity={0.8} color="#85f496" />
      <BackgroundParticles />
      {autoRotate && !focusNode && <AutoRotate />}
      {focusPos && isFinite(focusPos.x) && <CameraFocus target={[focusPos.x, focusPos.y, focusPos.z]} active={!!focusNode} />}
      <OrbitControls
        enableDamping
        dampingFactor={0.08}
        autoRotate={false}
        minDistance={5}
        maxDistance={100}
      />
      {nodes.map(n => {
        const p = positions[n.id];
        if (!p || !isFinite(p.x) || !isFinite(p.y) || !isFinite(p.z)) return null;
        const dimmed = highlightCategory ? n.category !== highlightCategory : false;
        return (
          <GraphNodeSphere
            key={n.id}
            node={n}
            position={[p.x, p.y, p.z]}
            onClick={onNodeClick}
            dimmed={dimmed}
          />
        );
      })}
      {edges.map((e, i) => {
        const s = positions[e.source], t = positions[e.target];
        if (!s || !t) return null;
        const sNode = nodes.find(n => n.id === e.source);
        const tNode = nodes.find(n => n.id === e.target);
        return (
          <GraphEdgeLine
            key={i}
            start={[s.x, s.y, s.z]}
            end={[t.x, t.y, t.z]}
            sourceColor={sNode ? getNodeColor(sNode.category, sNode.isHighlighted) : '#ffffff'}
            targetColor={tNode ? getNodeColor(tNode.category, tNode.isHighlighted) : '#ffffff'}
          />
        );
      })}
    </>
  );
}

const CATEGORY_LABELS: Record<string, [string, string]> = {
  skill: ['Skill', CATEGORY_COLORS.skill],
  main: ['ontoskill.ttl', CATEGORY_COLORS.main],
  prompt: ['Prompt', CATEGORY_COLORS.prompt],
  test: ['Test', CATEGORY_COLORS.test],
  module: ['Module', CATEGORY_COLORS.module],
  dependency: ['Depends on', CATEGORY_COLORS.dependency],
  AntiPattern: ['Anti-pattern', CATEGORY_COLORS.AntiPattern],
  RecoveryTactic: ['Recovery', CATEGORY_COLORS.RecoveryTactic],
  failure: ['Failure', CATEGORY_COLORS.failure],
  yield: ['Yields', CATEGORY_COLORS.yield],
  require: ['Requires', CATEGORY_COLORS.require],
  tool: ['Tool', CATEGORY_COLORS.tool],
  productivity: ['Productivity', CATEGORY_COLORS.productivity],
  development: ['Development', CATEGORY_COLORS.development],
};

const CATEGORY_DESCRIPTIONS: Record<string, string> = {
  skill: 'The root skill definition',
  main: 'Primary ontology file',
  prompt: 'Prompt template definitions',
  test: 'Test specifications',
  module: 'Additional ontology modules',
  dependency: 'Required skill dependencies',
  AntiPattern: 'Common mistakes to avoid',
  RecoveryTactic: 'Error recovery strategies',
  failure: 'Known failure modes',
  yield: 'States produced after execution',
  require: 'States required before execution',
  tool: 'Allowed tool integrations',
};

function KnowledgeGraph3D({ nodes, edges, onNodeClick, height = 350, selectedNode, highlightCategory, onHighlightCategory, t }: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  onNodeClick: (node: GraphNode) => void;
  height?: number;
  selectedNode?: GraphNode | null;
  highlightCategory?: string | null;
  onHighlightCategory?: (cat: string | null) => void;
  t: typeof translations.en;
}) {
  const [legendExpanded, setLegendExpanded] = useState(false);
  const [shortcutsVisible, setShortcutsVisible] = useState(false);

  if (!nodes.length) return null;
  const camDist = Math.max(nodes.length * 2.2, 30);
  const cats = [...new Set(nodes.map(n => n.category))];

  return (
    <div className="relative" style={{ width: '100%', height, borderRadius: '0.5rem', overflow: 'hidden', background: 'rgba(0,0,0,0.3)' }}>
      <Canvas camera={{ position: [0, 0, camDist], fov: 55 }} gl={{ alpha: true, antialias: true }}>
        <Scene
          nodes={nodes}
          edges={edges}
          onNodeClick={onNodeClick}
          highlightCategory={highlightCategory}
          focusNodeId={undefined}
        />
      </Canvas>
      {/* Expandable legend */}
      {cats.length > 1 && (
        <div className="absolute bottom-3 left-3 z-10">
          <div className="rounded-lg border border-white/[0.08] bg-[#090909]/90 backdrop-blur-md overflow-hidden">
            <div className="flex items-center gap-3 px-4 py-2.5">
              <span className="text-xs uppercase tracking-wider text-[#8a8a8a]">{t.legend}</span>
              {cats.map(c => {
                const color = getNodeColor(c, false);
                const label = CATEGORY_LABELS[c]?.[0] || c;
                return (
                  <button
                    key={c}
                    onClick={() => onHighlightCategory?.(highlightCategory === c ? null : c)}
                    className={`w-5 h-5 rounded-full border-2 transition-all duration-150 ${highlightCategory === c ? 'scale-125 border-white/40' : 'border-transparent hover:scale-110'}`}
                    style={{ background: color }}
                    title={label}
                  />
                );
              })}
              <button onClick={() => setLegendExpanded(!legendExpanded)} className="ml-1 text-[#8a8a8a] hover:text-[#d4d4d4] transition-colors">
                <svg className={`w-4 h-4 transition-transform ${legendExpanded ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
              </button>
            </div>
            {legendExpanded && (
              <div className="border-t border-white/[0.06] px-4 py-3 space-y-2.5 max-h-[70vh] overflow-y-auto">
                {cats.map(c => {
                  const color = getNodeColor(c, false);
                  const label = CATEGORY_LABELS[c]?.[0] || c;
                  return (
                    <div key={c} className="flex items-start gap-2.5">
                      <span className="w-3.5 h-3.5 rounded-full mt-0.5 shrink-0" style={{ background: color }} />
                      <div>
                        <span className="text-sm font-medium text-[#d4d4d4]">{label}</span>
                        <p className="text-xs text-[#8a8a8a] leading-relaxed">{CATEGORY_DESCRIPTIONS[c] || ''}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
      {/* Stats */}
      <div className="absolute top-4 right-4 text-sm text-[#8a8a8a] z-10">
        {nodes.length} {t.nodes} · {edges.length} {t.edges}
      </div>
      {/* Keyboard shortcuts */}
      <div className="absolute bottom-3 right-3 z-10">
        <div className="relative">
          <button
            onClick={() => setShortcutsVisible(!shortcutsVisible)}
            className="w-7 h-7 rounded-full bg-white/[0.04] border border-white/[0.08] text-[#8a8a8a] text-xs hover:bg-white/[0.08] hover:text-[#d4d4d4] transition-colors flex items-center justify-center"
          >
            ?
          </button>
          {shortcutsVisible && (
            <div className="absolute bottom-9 right-0 w-44 rounded-lg bg-[#090909]/95 backdrop-blur-md border border-white/[0.08] p-3 text-[11px] text-[#8a8a8a] space-y-1.5">
              <p className="text-[#d4d4d4] font-medium mb-1">{t.controls}</p>
              <p>Scroll = Zoom</p>
              <p>Drag = Orbit</p>
              <p>Right-drag = Pan</p>
              <p>Click node = Details</p>
              <p>Esc = Close</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Small Components ─────────────────────────────────────

function TrustBadge({ tier, t }: { tier: string; t: typeof translations.en }) {
  const styles: Record<string, string> = {
    official: 'bg-[#52c7e8]/10 text-[#52c7e8]',
    verified: 'bg-green-500/10 text-green-400',
    community: 'bg-amber-500/10 text-amber-400',
  };
  const labels: Record<string, string> = {
    official: t.official,
    verified: t.verified,
    community: t.community,
  };
  const cls = styles[tier] || 'bg-white/5 text-[#8a8a8a]';
  return <span className={`px-2.5 py-1 rounded-full text-xs font-medium uppercase tracking-wide ${cls}`}>{labels[tier] || tier}</span>;
}

function CopyButton({ text, t }: { text: string; t: typeof translations.en }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard?.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }).catch(() => {});
  };
  return (
    <button type="button" onClick={handleCopy} className="shrink-0 p-1.5 rounded hover:bg-white/5 opacity-40 hover:opacity-100 transition-opacity" title={t.copyToClipboard} aria-label={t.copyToClipboard}>
      {copied ? (
        <svg className="w-4 h-4 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
      ) : (
        <svg className="w-4 h-4 text-[#8a8a8a]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
      )}
    </button>
  );
}

function InstallBar({ command, t, id }: { command: string; t: typeof translations.en; id?: string }) {
  return (
    <div className={`flex items-center gap-2 px-3 py-2.5 rounded-lg bg-black/30 border border-white/5 ${id ? `group/${id}` : ''}`}>
      <code className="text-sm text-[#f5f5f5] font-mono break-all flex-1">{command}</code>
      <CopyButton text={command} t={t} />
    </div>
  );
}

// ─── Main App ─────────────────────────────────────────────

export default function OntoStoreApp({ lang = 'en' }: { lang?: string }) {
  const t = translations[lang as keyof typeof translations] || translations.en;
  const prefix = lang === 'zh' ? '/zh/ontostore' : '/ontostore';

  // Hide Astro loader placeholder on mount
  useEffect(() => {
    const el = document.getElementById('ontostore-loader');
    if (el) el.remove();
  }, []);

  const [skills, setSkills] = useState<Skill[]>([]);
  const [packages, setPackages] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  // Routing
  const [viewMode, setViewMode] = useState<ViewMode>('store');
  const [authorId, setAuthorId] = useState('');
  const [pkgId, setPkgId] = useState('');
  const [skillId, setSkillId] = useState('');
  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [filterAuthor, setFilterAuthor] = useState('');
  const [filterCategory, setFilterCategory] = useState('');
  const [filterTier, setFilterTier] = useState('');
  const [filterSort, setFilterSort] = useState('az');
  const [visibleCount, setVisibleCount] = useState(20);

  // Derived data
  const meta = useMemo(() => ({
    authors: [...new Set(skills.map(s => s.author))].sort(),
    categories: [...new Set(skills.map(s => s.category).filter(Boolean))].sort(),
    trustTiers: [...new Set(skills.map(s => s.trustTier))].sort(),
  }), [skills]);

  const filteredSkills = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return skills.filter(s => {
      if (q) {
        const h = [s.packageId, s.skillId, s.qualifiedId, s.description, s.aliases.join(' '), s.category, s.intents.join(' ')].join(' ').toLowerCase();
        if (!h.includes(q)) return false;
      }
      if (filterAuthor && s.author !== filterAuthor) return false;
      if (filterCategory && s.category !== filterCategory) return false;
      if (filterTier && s.trustTier !== filterTier) return false;
      return true;
    }).sort((a, b) => filterSort === 'za' ? b.qualifiedId.localeCompare(a.qualifiedId) : a.qualifiedId.localeCompare(b.qualifiedId));
  }, [skills, searchQuery, filterAuthor, filterCategory, filterTier, filterSort]);

  // Fetch data
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await fetch(STORE_INDEX_URL, { mode: 'cors', headers: { Accept: 'application/json' } });
        if (!res.ok) throw new Error(`Index failed: ${res.status}`);
        const data = await res.json();
        const results = await Promise.allSettled(
          (data.packages || []).map(async (entry: any) => {
            const url = new URL(entry.manifest_path, STORE_INDEX_URL).toString();
            const r = await fetch(url, { mode: 'cors', headers: { Accept: 'application/json' } });
            if (!r.ok) throw new Error(`Manifest failed: ${r.status}`);
            return r.json();
          })
        );
        if (cancelled) return;
        const manifests = results.filter(r => r.status === 'fulfilled').map(r => (r as any).value);
        setPackages(manifests);
        const newSkills = manifests.flatMap(pkg => (pkg.skills || []).map((s: any) => normSkill(pkg, s)));
        newSkills.sort((a, b) => a.qualifiedId.localeCompare(b.qualifiedId));
        setSkills(newSkills);
        setLoading(false);
      } catch {
        if (!cancelled) { setError(true); setLoading(false); }
      }
    };
    load();
    return () => { cancelled = true; };
  }, []);

  // Route from URL
  useEffect(() => {
    const parse = () => {
      // Restore redirect path from 404 page (dev mode SPA fallback)
      let path = window.location.pathname.replace(/\/$/, '');
      try {
        const saved = sessionStorage.getItem('ontostore:redirect');
        if (saved) { sessionStorage.removeItem('ontostore:redirect'); history.replaceState(null, '', saved); path = saved.replace(/\/$/, ''); }
      } catch {}
      const storePath = path.replace(prefix, '').replace(/^\//, '');
      const segments = storePath ? storePath.split('/') : [];
      if (segments.length === 0) { setViewMode('store'); }
      else if (segments.length === 1) { setViewMode('author'); setAuthorId(segments[0]); }
      else if (segments.length === 2) { setViewMode('package'); setPkgId(segments.join('/')); }
      else { setViewMode('skill'); setPkgId(segments.slice(0, 2).join('/')); setSkillId(segments.slice(2).join('/')); }
    };
    parse();
    window.addEventListener('popstate', parse);
    return () => window.removeEventListener('popstate', parse);
  }, [prefix]);

  const navigate = useCallback((href: string) => {
    history.pushState(null, '', href);
    window.dispatchEvent(new PopStateEvent('popstate'));
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, []);

  const navClick = useCallback((href: string) => (e: React.MouseEvent) => {
    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    navigate(href);
  }, [navigate]);

  // Reset filters when view changes
  useEffect(() => {
    setVisibleCount(20);
    setSearchQuery('');
    setFilterAuthor('');
    setFilterCategory('');
    setFilterTier('');
    setFilterSort('az');
  }, [viewMode]);

  // ─── Render ───────────────────────────────────────────────

  if (error) {
    return (
      <div className="text-center py-20">
        <p className="text-[#d4d4d4] mb-4">{t.unableToLoad}</p>
        <button onClick={() => window.location.reload()} className="px-4 py-2 rounded-lg bg-[#52c7e8]/10 text-[#52c7e8] hover:bg-[#52c7e8]/20 transition-colors">{t.retry}</button>
      </div>
    );
  }

  return (
    <div className="ontoskills-store-root overflow-x-hidden">
      <div className="store-glow" />
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 relative">
        {viewMode === 'store' && <StoreView loading={loading} skills={skills} filteredSkills={filteredSkills} meta={meta} t={t} prefix={prefix} navigate={navigate} searchQuery={searchQuery} setSearchQuery={setSearchQuery} filterAuthor={filterAuthor} setFilterAuthor={setFilterAuthor} filterCategory={filterCategory} setFilterCategory={setFilterCategory} filterTier={filterTier} setFilterTier={setFilterTier} filterSort={filterSort} setFilterSort={setFilterSort} visibleCount={visibleCount} setVisibleCount={setVisibleCount} lang={lang} />}
        {viewMode === 'author' && <AuthorView loading={loading} skills={skills} authorId={authorId} t={t} prefix={prefix} navigate={navigate} />}
        {viewMode === 'package' && <PackageView loading={loading} skills={skills} packages={packages} pkgId={pkgId} t={t} prefix={prefix} navigate={navigate} />}
        {viewMode === 'skill' && <SkillDetailView skills={skills} packages={packages} pkgId={pkgId} skillId={skillId} t={t} prefix={prefix} navigate={navigate} lang={lang} />}
      </div>
    </div>
  );
}

// ─── Store View ───────────────────────────────────────────

function StoreView({ loading, skills, filteredSkills, meta, t, prefix, navigate, searchQuery, setSearchQuery, filterAuthor, setFilterAuthor, filterCategory, setFilterCategory, filterTier, setFilterTier, filterSort, setFilterSort, visibleCount, setVisibleCount, lang }: any) {
  const docsLink = lang === 'zh' ? '/zh/docs/getting-started/' : '/docs/getting-started/';
  const visible = filteredSkills.slice(0, visibleCount);
  const remaining = filteredSkills.length - visibleCount;

  return (
    <>
      <div className="mb-10">
        <h2 className="text-2xl sm:text-3xl font-bold text-[#f5f5f5] mb-2">{t.storeLabel}</h2>
        <p className="text-base text-[#d4d4d4]">{t.allSkills}</p>
      </div>

      {/* Get Started — minimal */}
      <div className="mb-8 inline-flex flex-col sm:flex-row sm:items-center gap-4 p-4 rounded-lg bg-white/[0.02] border border-white/[0.06]">
        <span className="text-sm text-[#8a8a8a] shrink-0">{t.getStarted}</span>
        <InstallBar command={t.setupMcpCommand} t={t} id="gs1" />
        <InstallBar command={t.setupSkillCommand} t={t} id="gs2" />
        <a href={docsLink} className="text-sm text-[#52c7e8] hover:underline shrink-0">{t.setupDocs} →</a>
      </div>

      {/* Search + filters */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between mb-6">
        <div className="relative flex-1 sm:max-w-md">
          <svg className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-[#8a8a8a]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
          <input className="w-full bg-white/[0.04] border border-white/10 rounded-lg pl-10 pr-4 py-2.5 text-sm text-[#f5f5f5] outline-none placeholder:text-[#8a8a8a] focus:border-[#52c7e8]/50 transition-colors" type="search" placeholder={t.searchPlaceholder} value={searchQuery} onChange={e => setSearchQuery(e.target.value)} />
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <select value={filterAuthor} onChange={e => setFilterAuthor(e.target.value)} className="bg-white/[0.04] border border-white/10 rounded-lg pl-2.5 pr-7 py-2 text-sm text-[#d4d4d4] outline-none cursor-pointer hover:border-white/20 focus:border-[#52c7e8]/50 transition-colors appearance-none bg-[length:12px] bg-[right_8px_center] bg-no-repeat" style={{ colorScheme: 'dark', backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%238a8a8a' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E\")" }} aria-label={t.author}>
            <option value="">{t.allAuthors}</option>
            {meta.authors.map((a: string) => <option key={a} value={a}>{a}</option>)}
          </select>
          <select value={filterCategory} onChange={e => setFilterCategory(e.target.value)} className="bg-white/[0.04] border border-white/10 rounded-lg pl-2.5 pr-7 py-2 text-sm text-[#d4d4d4] outline-none cursor-pointer hover:border-white/20 focus:border-[#52c7e8]/50 transition-colors appearance-none bg-[length:12px] bg-[right_8px_center] bg-no-repeat" style={{ colorScheme: 'dark', backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%238a8a8a' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E\")" }} aria-label={t.category}>
            <option value="">{t.allCategories}</option>
            {meta.categories.map((c: string) => <option key={c} value={c}>{c}</option>)}
          </select>
          <select value={filterTier} onChange={e => setFilterTier(e.target.value)} className="bg-white/[0.04] border border-white/10 rounded-lg pl-2.5 pr-7 py-2 text-sm text-[#d4d4d4] outline-none cursor-pointer hover:border-white/20 focus:border-[#52c7e8]/50 transition-colors appearance-none bg-[length:12px] bg-[right_8px_center] bg-no-repeat" style={{ colorScheme: 'dark', backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%238a8a8a' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E\")" }} aria-label={t.trustTier}>
            <option value="">{t.allTiers}</option>
            {meta.trustTiers.map((tier: string) => <option key={tier} value={tier}>{tier === 'official' ? t.official : tier === 'verified' ? t.verified : tier === 'community' ? t.community : tier}</option>)}
          </select>
          <select value={filterSort} onChange={e => setFilterSort(e.target.value)} className="bg-white/[0.04] border border-white/10 rounded-lg pl-2.5 pr-7 py-2 text-sm text-[#d4d4d4] outline-none cursor-pointer hover:border-white/20 focus:border-[#52c7e8]/50 transition-colors appearance-none bg-[length:12px] bg-[right_8px_center] bg-no-repeat" style={{ colorScheme: 'dark', backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%238a8a8a' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E\")" }} aria-label={t.sort}>
            <option value="az">{t.sortAZ}</option>
            <option value="za">{t.sortZA}</option>
          </select>
          <span className="text-sm text-[#8a8a8a] ml-2">{filteredSkills.length} {filteredSkills.length === 1 ? t.skill_one : t.skill_other}</span>
        </div>
      </div>

      {/* Grid */}
      {loading ? (
        <div className="flex items-center justify-center py-20 gap-3">
          <div className="w-5 h-5 border-2 border-[#52c7e8]/30 border-t-[#52c7e8] rounded-full animate-spin"></div>
          <p className="text-[#8a8a8a] text-sm">{t.connecting}</p>
        </div>
      ) : !filteredSkills.length ? (
        <div className="py-16 text-center">
          <p className="text-[#d4d4d4] mb-2">{t.noMatch}</p>
          <p className="text-sm text-[#8a8a8a]">{t.trySearch}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {visible.map(s => <SkillCard key={s.qualifiedId} skill={s} t={t} prefix={prefix} navigate={navigate} />)}
        </div>
      )}

      {/* Load more */}
      {remaining > 0 && (
        <div className="mt-8 text-center">
          <button onClick={() => setVisibleCount(c => c + 20)} className="px-6 py-2.5 rounded-lg bg-white/[0.04] border border-white/10 text-sm text-[#d4d4d4] hover:bg-white/[0.08] hover:border-white/20 transition-colors">
            {t.loadMore} ({remaining} {t.remaining})
          </button>
        </div>
      )}
    </>
  );
}

// ─── Skill Card ───────────────────────────────────────────

function SkillCard({ skill, t, prefix, navigate }: { skill: Skill; t: typeof translations.en; prefix: string; navigate: (href: string) => void }) {
  return (
    <a
      href={`${prefix}/${skill.qualifiedId}`}
      onClick={navClick(`${prefix}/${skill.qualifiedId}`)}
      className="skill-card block rounded-xl border border-white/[0.07] bg-white/[0.02] p-5 flex flex-col gap-3 cursor-pointer hover:border-[#52c7e8]/30 hover:bg-[#52c7e8]/[0.04] hover:-translate-y-0.5 hover:shadow-[0_6px_24px_rgba(0,0,0,0.3)] transition-all duration-200"
    >
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-base font-semibold text-[#f5f5f5] leading-tight">{skill.skillId}</h3>
        <TrustBadge tier={skill.trustTier} t={t} />
      </div>
      <code className="text-xs text-[#8a8a8a] font-mono">{skill.qualifiedId}</code>
      <p className="skill-desc text-sm text-[#d4d4d4] leading-relaxed flex-1">{skill.description}</p>
      <div className="flex flex-wrap gap-1.5">
        {skill.category && <span className="px-2.5 py-0.5 rounded-full bg-white/5 text-xs text-[#8a8a8a]">{skill.category}</span>}
        {skill.aliases.slice(0, 3).map(a => <span key={a} className="px-2 py-0.5 rounded-full bg-white/5 text-xs text-[#8a8a8a]">{a}</span>)}
      </div>
      <InstallBar command={skill.installCommand} t={t} id={`card-${skill.qualifiedId}`} />
    </a>
  );
}

// ─── Author View ──────────────────────────────────────────

function AuthorView({ loading, skills, authorId, t, prefix, navigate }: { loading: boolean; skills: Skill[]; authorId: string; t: typeof translations.en; prefix: string; navigate: (href: string) => void }) {
  const authorSkills = skills.filter(s => s.author === authorId);
  const pkgMap: Record<string, Skill[]> = {};
  authorSkills.forEach(s => { pkgMap[s.packageId] = pkgMap[s.packageId] || []; pkgMap[s.packageId].push(s); });
  const allCats = [...new Set(authorSkills.map(s => s.category).filter(Boolean))];
  const tierCounts = authorSkills.reduce<Record<string, number>>((acc, s) => { acc[s.trustTier] = (acc[s.trustTier] || 0) + 1; return acc; }, {});

  return (
    <>
      <div className="breadcrumb flex items-center gap-2 text-sm mb-8">
        <a href={prefix} onClick={navClick(prefix)} className="text-[#8a8a8a] hover:text-[#52c7e8] transition-colors">{t.storeLabel}</a>
        <span className="text-[#8a8a8a]">/</span>
        <span className="text-[#f5f5f5] font-medium">{authorId}</span>
      </div>
      <div className="mb-10">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div>
            <h2 className="text-2xl sm:text-3xl font-bold text-[#f5f5f5] mb-2">{authorId}</h2>
            <p className="text-sm text-[#8a8a8a]">{authorSkills.length} {t.totalSkills} · {Object.keys(pkgMap).length} {t.packages.toLowerCase()}</p>
          </div>
          <InstallBar command={`npx ontoskills install ${authorId}/<package>`} t={t} id="authInstall" />
        </div>
        {/* Stats row */}
        <div className="flex flex-wrap gap-3 mt-4">
          {allCats.map(c => (
            <span key={c} className="px-3 py-1.5 rounded-lg bg-white/[0.03] border border-white/[0.07] text-xs text-[#d4d4d4]">{c}</span>
          ))}
          {Object.entries(tierCounts).map(([tier, count]) => (
            <span key={tier} className="px-3 py-1.5 rounded-lg bg-white/[0.03] border border-white/[0.07] text-xs text-[#8a8a8a]">{tier}: {count}</span>
          ))}
        </div>
      </div>
      {loading ? (
        <div className="flex items-center justify-center py-16 gap-3">
          <div className="w-5 h-5 border-2 border-[#52c7e8]/30 border-t-[#52c7e8] rounded-full animate-spin"></div>
          <p className="text-[#8a8a8a] text-sm">{t.connecting}</p>
        </div>
      ) : Object.entries(pkgMap).map(([pid, pkgSkills]) => {
        const tier = pkgSkills[0]?.trustTier || 'verified';
        const ver = pkgSkills[0]?.version || '';
        const pkgName = pid.split('/').slice(1).join('/');
        const cats = [...new Set(pkgSkills.map(s => s.category).filter(Boolean))];
        return (
          <div key={pid} className="mb-6 p-5 rounded-xl border border-white/[0.07] bg-white/[0.02] hover:border-white/[0.12] transition-colors">
            <div className="flex items-center gap-3 mb-3">
              <a href={`${prefix}/${pid}`} onClick={navClick(`${prefix}/${pid}`)} className="text-xl font-semibold text-[#f5f5f5] hover:text-[#52c7e8] transition-colors">{pkgName}</a>
              <TrustBadge tier={tier} t={t} />
              {ver && <span className="text-xs text-[#8a8a8a]">v{ver}</span>}
            </div>
            <div className="flex items-center gap-3 mb-3">
              <span className="text-sm text-[#8a8a8a]">{pkgSkills.length} {t.skills.toLowerCase()}</span>
              <span className="text-[#8a8a8a]">·</span>
              <div className="flex flex-wrap gap-1.5">
                {cats.map(c => <span key={c} className="px-2 py-0.5 rounded-full bg-white/5 text-xs text-[#8a8a8a]">{c}</span>)}
              </div>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {pkgSkills.slice(0, 6).map(s => (
                <a
                  key={s.qualifiedId}
                  href={`${prefix}/${s.qualifiedId}`}
                  onClick={navClick(`${prefix}/${s.qualifiedId}`)}
                  className="px-3 py-2 rounded-lg bg-white/[0.02] border border-white/[0.05] text-sm text-[#d4d4d4] hover:border-[#52c7e8]/30 hover:text-[#52c7e8] transition-colors truncate"
                >
                  {s.skillId}
                </a>
              ))}
              {pkgSkills.length > 6 && (
                <a href={`${prefix}/${pid}`} onClick={navClick(`${prefix}/${pid}`)} className="px-3 py-2 rounded-lg bg-white/[0.02] border border-white/[0.05] text-sm text-[#8a8a8a] hover:text-[#52c7e8] transition-colors">
                  +{pkgSkills.length - 6} more
                </a>
              )}
            </div>
          </div>
        );
      })}
    </>
  );
}

// ─── Package View ─────────────────────────────────────────

function PackageView({ loading, skills, packages, pkgId, t, prefix, navigate }: { loading: boolean; skills: Skill[]; packages: any[]; pkgId: string; t: typeof translations.en; prefix: string; navigate: (href: string) => void }) {
  const pkgSkills = skills.filter(s => s.packageId === pkgId);
  const author = pkgId.split('/')[0];
  const pkgName = pkgId.split('/').slice(1).join('/');
  const tier = pkgSkills[0]?.trustTier || 'verified';
  const ver = pkgSkills[0]?.version || '';
  const rawPkg = packages.find(p => p.package_id === pkgId);
  const modules: string[] = rawPkg?.modules || [];
  const hasDeps = packageHasDeps(pkgSkills);
  const graphData = useMemo(() => hasDeps ? buildGraphData(pkgSkills) : null, [pkgSkills, hasDeps]);

  const handleGraphNodeClick = useCallback((node: GraphNode) => {
    const skill = skills.find(s => s.packageId === pkgId && s.skillId === node.id);
    if (skill) navigate(`${prefix}/${skill.qualifiedId}`);
  }, [navigate, prefix, pkgId, skills]);

  return (
    <>
      <div className="breadcrumb flex items-center gap-2 text-sm mb-8">
        <a href={prefix} onClick={navClick(prefix)} className="text-[#8a8a8a] hover:text-[#52c7e8] transition-colors">{t.storeLabel}</a>
        <span className="text-[#8a8a8a]">/</span>
        <a href={`${prefix}/${author}`} onClick={navClick(`${prefix}/${author}`)} className="text-[#8a8a8a] hover:text-[#52c7e8] transition-colors">{author}</a>
        <span className="text-[#8a8a8a]">/</span>
        <span className="text-[#f5f5f5] font-medium">{pkgName}</span>
      </div>
      <div className="mb-8">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 mb-4">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <h2 className="text-2xl sm:text-3xl font-bold text-[#f5f5f5]">{pkgName}</h2>
              <TrustBadge tier={tier} t={t} />
              {ver && <span className="text-sm text-[#8a8a8a]">v{ver}</span>}
            </div>
            <code className="text-sm text-[#8a8a8a] font-mono">{pkgId}</code>
            <div className="flex items-center gap-3 mt-2">
              <span className="text-sm text-[#8a8a8a]">{pkgSkills.length} {t.skills.toLowerCase()}</span>
              <span className="text-[#8a8a8a]">·</span>
              <span className="text-sm text-[#8a8a8a]">{modules.length} {t.files_other}</span>
            </div>
            {rawPkg?.description && <p className="text-sm text-[#d4d4d4] mt-3 leading-relaxed">{rawPkg.description}</p>}
          </div>
          <InstallBar command={`npx ontoskills install ${pkgId}`} t={t} id="pkgInstall" />
        </div>
      </div>
      {hasDeps && graphData && (
        <div className="section-panel mb-6">
          <h3>{t.knowledgeGraph}</h3>
          <KnowledgeGraph3D nodes={graphData.nodes} edges={graphData.edges} onNodeClick={handleGraphNodeClick} height={350} t={t} />
        </div>
      )}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          {loading ? (
            <div className="flex items-center justify-center py-16 gap-3">
              <div className="w-5 h-5 border-2 border-[#52c7e8]/30 border-t-[#52c7e8] rounded-full animate-spin"></div>
              <p className="text-[#8a8a8a] text-sm">{t.connecting}</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              {pkgSkills.map(s => <SkillCard key={s.qualifiedId} skill={s} t={t} prefix={prefix} navigate={navigate} />)}
            </div>
          )}
        </div>
        <div className="space-y-4">
          <div className="section-panel">
            <h3>{t.fileTree} ({modules.length})</h3>
            <div className="max-h-80 overflow-y-auto text-sm">
              <FileTree modules={modules} />
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

// ─── Skill Detail View ────────────────────────────────────

function SkillDetailView({ skills, packages, pkgId, skillId, t, prefix, navigate, lang }: { skills: Skill[]; packages: any[]; pkgId: string; skillId: string; t: typeof translations.en; prefix: string; navigate: (href: string) => void; lang: string }) {
  const skill = skills.find(s => s.packageId === pkgId && s.skillId === skillId);
  const rawPkg = packages.find(p => p.package_id === pkgId);
  const modules: string[] = rawPkg?.modules || [];
  const skillModules = modules.filter(m => m.startsWith(skillId + '/') || m === `${skillId}/ontoskill.ttl`);
  const treeModules = skillModules.length ? skillModules : modules.filter(m => m.startsWith(skillId));

  // Graph state
  const [showGraph, setShowGraph] = useState(false);
  const [graphMode, setGraphMode] = useState<'files' | 'knowledge'>('files');
  const [knowledgeData, setKnowledgeData] = useState<{ nodes: GraphNode[]; edges: GraphEdge[] } | null>(null);
  const [loadingKnowledge, setLoadingKnowledge] = useState(false);
  const [graphError, setGraphError] = useState(false);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [highlightCategory, setHighlightCategory] = useState<string | null>(null);
  const [graphBreadcrumb, setGraphBreadcrumb] = useState<Array<{ label: string; fileId: string | null }>>([
    { label: skillId, fileId: null },
  ]);

  // File graph — built synchronously from module list
  const fileGraphData = useMemo(() => buildFileGraphData(treeModules, skillId), [treeModules, skillId]);

  // Fetch TTL content and parse knowledge map
  const loadKnowledgeGraph = useCallback(async () => {
    if (knowledgeData) return;
    setLoadingKnowledge(true);
    setGraphError(false);
    try {
      const ttlBase = `${TTL_BASE}${pkgId}/`;
      const ttlFiles = treeModules.filter(m => m.endsWith('.ttl'));
      const contents: string[] = [];
      await Promise.all(ttlFiles.map(async (f) => {
        try {
          const res = await fetch(ttlBase + f);
          if (res.ok) contents.push(await res.text());
        } catch { /* skip failed files */ }
      }));
      if (!contents.length) { setGraphError(true); return; }
      setKnowledgeData(parseTtlKnowledgeMap(contents.join('\n'), skillId));
    } catch { setGraphError(true); }
    finally { setLoadingKnowledge(false); }
  }, [pkgId, treeModules, skillId, knowledgeData]);

  const openGraph = useCallback(() => {
    if (graphMode === 'knowledge' && !knowledgeData) {
      loadKnowledgeGraph().then(() => setShowGraph(true));
    } else {
      setShowGraph(true);
    }
  }, [graphMode, knowledgeData, loadKnowledgeGraph]);

  // Explore a secondary TTL file's knowledge map
  const exploreSecondaryFile = useCallback(async (node: GraphNode) => {
    const fileId = node.qualifiedId;
    if (!fileId.endsWith('.ttl')) return;
    setLoadingKnowledge(true);
    setGraphError(false);
    try {
      const res = await fetch(`${TTL_BASE}${pkgId}/${fileId}`);
      if (!res.ok) throw new Error(`Failed: ${res.status}`);
      const content = await res.text();
      const parsed = parseTtlKnowledgeMap(content, fileId.split('/').pop()!.replace('.ttl', ''));
      setKnowledgeData(parsed);
      setGraphMode('knowledge');
      setGraphBreadcrumb(prev => [...prev, { label: node.label, fileId }]);
      setSelectedNode(null);
    } catch { setGraphError(true); }
    finally { setLoadingKnowledge(false); }
  }, [pkgId]);

  const activeGraphData = graphMode === 'files' ? fileGraphData : knowledgeData;

  if (!skill) {
    return <div className="text-center py-20"><p className="text-[#d4d4d4] text-lg">{t.noMatch}</p></div>;
  }

  const author = pkgId.split('/')[0];
  const pkgName = pkgId.split('/').slice(1).join('/');

  return (
    <>
      {/* Fullscreen 3D graph overlay */}
      {showGraph && activeGraphData && (
        <div className="fixed inset-0 z-50 bg-[#090909] flex flex-col">
          <div className="flex items-center justify-between px-6 py-4 border-b border-white/10">
            <div className="flex flex-col gap-1">
              {/* Breadcrumb */}
              <div className="flex items-center gap-1.5 text-xs">
                {graphBreadcrumb.map((crumb, i) => (
                  <span key={i} className="flex items-center gap-1.5">
                    {i > 0 && <svg className="w-3 h-3 text-[#8a8a8a]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>}
                    <button
                      onClick={() => {
                        if (i < graphBreadcrumb.length - 1) {
                          setGraphBreadcrumb(prev => prev.slice(0, i + 1));
                          if (i === 0) setGraphMode('files');
                        }
                      }}
                      className={`transition-colors ${i === graphBreadcrumb.length - 1 ? 'text-[#f5f5f5] font-medium' : 'text-[#8a8a8a] hover:text-[#52c7e8]'}`}
                    >
                      {crumb.label}
                    </button>
                  </span>
                ))}
              </div>
              <div className="flex items-center gap-4">
                <h3 className="text-lg font-semibold text-[#f5f5f5]">{graphMode === 'files' ? t.fileGraph : t.knowledgeMap}</h3>
                <div className="flex gap-1 bg-white/5 rounded-lg p-0.5">
                  <button onClick={() => setGraphMode('files')} className={`px-3 py-1 rounded-md text-xs transition-colors ${graphMode === 'files' ? 'bg-[#52c7e8]/20 text-[#52c7e8]' : 'text-[#8a8a8a] hover:text-[#d4d4d4]'}`}>{t.fileGraph}</button>
                  <button onClick={async () => { setGraphMode('knowledge'); if (!knowledgeData) await loadKnowledgeGraph(); }} className={`px-3 py-1 rounded-md text-xs transition-colors ${graphMode === 'knowledge' ? 'bg-[#52c7e8]/20 text-[#52c7e8]' : 'text-[#8a8a8a] hover:text-[#d4d4d4]'}`}>{t.knowledgeMap}</button>
                </div>
              </div>
            </div>
            <button onClick={() => { setShowGraph(false); setSelectedNode(null); }} className="p-2 rounded-lg hover:bg-white/10 text-[#8a8a8a] hover:text-[#f5f5f5] transition-colors">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          </div>
          <div className="flex-1 relative">
            {loadingKnowledge ? (
              <div className="flex items-center justify-center h-full gap-3">
                <div className="w-5 h-5 border-2 border-[#52c7e8]/30 border-t-[#52c7e8] rounded-full animate-spin" />
                <p className="text-[#8a8a8a] text-sm">{t.loadingGraph}</p>
              </div>
            ) : graphError ? (
              <div className="flex items-center justify-center h-full"><p className="text-[#f9a8d4]">{t.graphError}</p></div>
            ) : (
              <KnowledgeGraph3D
                nodes={activeGraphData.nodes}
                edges={activeGraphData.edges}
                onNodeClick={setSelectedNode}
                selectedNode={selectedNode}
                highlightCategory={highlightCategory}
                onHighlightCategory={setHighlightCategory}
                height={window.innerHeight - 64}
                t={t}
              />
            )}
            {/* Node detail panel */}
            {selectedNode && (
              <div className="absolute right-0 top-0 bottom-0 w-[360px] bg-[#0d0d14]/95 backdrop-blur-md border-l border-white/[0.08] overflow-y-auto z-20"
                style={{ animation: 'slideIn 0.25s ease-out' }}
              >
                {/* Header */}
                <div className="px-5 pt-5 pb-4 border-b border-white/[0.07]">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="w-3 h-3 rounded-full" style={{ background: getNodeColor(selectedNode.category, selectedNode.isHighlighted) }} />
                      <span className="text-xs uppercase tracking-widest text-[#8a8a8a]">
                        {CATEGORY_LABELS[selectedNode.category]?.[0] || selectedNode.category}
                      </span>
                    </div>
                    <button onClick={() => setSelectedNode(null)} className="p-1.5 rounded-lg hover:bg-white/10 text-[#8a8a8a] transition-colors">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                    </button>
                  </div>
                  <h2 className="text-lg font-bold text-[#f5f5f5] break-words">{selectedNode.label}</h2>
                  {CATEGORY_DESCRIPTIONS[selectedNode.category] && (
                    <p className="text-xs text-[#666] mt-1.5">{CATEGORY_DESCRIPTIONS[selectedNode.category]}</p>
                  )}
                </div>

                {/* Description / Value */}
                {selectedNode.description && (
                  <div className="px-5 py-4 border-b border-white/[0.05]">
                    <h3 className="text-xs uppercase tracking-widest text-[#8a8a8a] mb-2">Value</h3>
                    <p className="text-sm text-[#d4d4d4] leading-relaxed break-words">{selectedNode.description}</p>
                  </div>
                )}

                {/* Properties */}
                <div className="px-5 py-4 border-b border-white/[0.05]">
                  <h3 className="text-xs uppercase tracking-widest text-[#8a8a8a] mb-3">Properties</h3>
                  <div className="space-y-2.5">
                    <div className="flex items-start gap-3">
                      <span className="text-xs text-[#8a8a8a] shrink-0 w-14">Type</span>
                      <div className="flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full" style={{ background: getNodeColor(selectedNode.category, selectedNode.isHighlighted) }} />
                        <span className="text-xs text-[#d4d4d4]">{CATEGORY_LABELS[selectedNode.category]?.[0] || selectedNode.category}</span>
                      </div>
                    </div>
                    <div className="flex items-start gap-3">
                      <span className="text-xs text-[#8a8a8a] shrink-0 w-14">ID</span>
                      <code className="text-xs text-[#d4d4d4] font-mono break-all leading-relaxed">{selectedNode.qualifiedId || selectedNode.id}</code>
                    </div>
                    {selectedNode.category === 'dependency' && (() => {
                      const depName = selectedNode.qualifiedId.replace(/^dep:/, '').replace(/_/g, '-');
                      return (
                        <div className="flex items-start gap-3">
                          <span className="text-xs text-[#8a8a8a] shrink-0 w-14">Skill</span>
                          <span className="text-xs text-[#d4d4d4]">{depName}</span>
                        </div>
                      );
                    })()}
                    {(['yield', 'require'].includes(selectedNode.category)) && selectedNode.description && (
                      <div className="flex items-start gap-3">
                        <span className="text-xs text-[#8a8a8a] shrink-0 w-14">State</span>
                        <span className="text-xs text-[#d4d4d4] break-words">{selectedNode.description}</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Connected nodes */}
                <div className="px-5 py-4 border-b border-white/[0.05]">
                  <h3 className="text-xs uppercase tracking-widest text-[#8a8a8a] mb-3">Connected to</h3>
                  {(() => {
                    const connected = getConnectedNodes(selectedNode, activeGraphData.edges, activeGraphData.nodes);
                    if (!connected.length) return <p className="text-xs text-[#666]">No connections</p>;
                    return (
                      <div className="flex flex-wrap gap-2">
                        {connected.map(n => (
                          <button
                            key={n.id}
                            onClick={() => setSelectedNode(n)}
                            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-white/[0.04] border border-white/[0.07] text-xs text-[#d4d4d4] hover:border-[#52c7e8]/30 hover:text-[#52c7e8] transition-colors"
                          >
                            <span className="w-2 h-2 rounded-full shrink-0" style={{ background: getNodeColor(n.category, n.isHighlighted) }} />
                            {n.label}
                          </button>
                        ))}
                      </div>
                    );
                  })()}
                </div>

                {/* Actions: explore file / view skill */}
                {(() => {
                  const isTtlFile = ['main', 'prompt', 'test', 'module'].includes(selectedNode.category) && selectedNode.qualifiedId.endsWith('.ttl');
                  const depSkill = skills.find(s => s.packageId === pkgId && s.skillId === selectedNode.id);
                  return (
                    <div className="px-5 py-4 space-y-2">
                      {isTtlFile && (
                        <button
                          onClick={() => exploreSecondaryFile(selectedNode)}
                          className="w-full py-2.5 rounded-lg bg-[#52c7e8]/10 text-[#52c7e8] text-sm font-medium hover:bg-[#52c7e8]/20 transition-colors flex items-center justify-center gap-2"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
                          Open knowledge map
                        </button>
                      )}
                      {depSkill && (
                        <button
                          onClick={() => { setShowGraph(false); setSelectedNode(null); navigate(`${prefix}/${depSkill.qualifiedId}`); }}
                          className="w-full py-2.5 rounded-lg bg-white/[0.04] border border-white/[0.07] text-sm text-[#d4d4d4] hover:border-[#52c7e8]/30 hover:text-[#52c7e8] transition-colors"
                        >
                          View skill →
                        </button>
                      )}
                    </div>
                  );
                })()}
              </div>
            )}
          </div>
        </div>
      )}

      <div className="breadcrumb flex items-center gap-2 text-sm mb-8">
        <a href={prefix} onClick={navClick(prefix)} className="text-[#8a8a8a] hover:text-[#52c7e8] transition-colors">{t.storeLabel}</a>
        <span className="text-[#8a8a8a]">/</span>
        <a href={`${prefix}/${author}`} onClick={navClick(`${prefix}/${author}`)} className="text-[#8a8a8a] hover:text-[#52c7e8] transition-colors">{author}</a>
        <span className="text-[#8a8a8a]">/</span>
        <a href={`${prefix}/${pkgId}`} onClick={navClick(`${prefix}/${pkgId}`)} className="text-[#8a8a8a] hover:text-[#52c7e8] transition-colors">{pkgName}</a>
        <span className="text-[#8a8a8a]">/</span>
        <span className="text-[#f5f5f5] font-medium">{skillId}</span>
      </div>
      <div className="mb-8">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 mb-4">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <h2 className="text-2xl sm:text-3xl font-bold text-[#f5f5f5]">{skillId}</h2>
              <TrustBadge tier={skill.trustTier} t={t} />
              {skill.version && <span className="text-sm text-[#8a8a8a]">v{skill.version}</span>}
              {skill.category && <span className="px-2.5 py-1 rounded-full bg-white/5 text-xs text-[#8a8a8a]">{skill.category}</span>}
            </div>
            <code className="text-sm text-[#8a8a8a] font-mono">{skill.qualifiedId}</code>
          </div>
          <InstallBar command={skill.installCommand} t={t} id="skillInstall" />
        </div>
        <p className="text-base text-[#d4d4d4] leading-relaxed">{skill.description}</p>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          {skill.intents.length > 0 && (
            <div className="section-panel">
              <h3>{t.intents}</h3>
              <ul className="space-y-2">
                {skill.intents.map(i => (
                  <li key={i} className="flex items-start gap-2 text-sm text-[#d4d4d4]">
                    <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-[#52c7e8] shrink-0" />
                    {i}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {skill.dependsOn.length > 0 && (
            <div className="section-panel">
              <h3>{t.dependencies}</h3>
              <div className="flex flex-wrap gap-2">
                {skill.dependsOn.map(d => {
                  const dep = skills.find(s => s.packageId === pkgId && s.skillId === d);
                  if (!dep) return (
                    <span key={d} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/[0.03] text-sm text-[#8a8a8a]">
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.172 13.828a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.102 1.101" /></svg>
                      {d}
                    </span>
                  );
                  return (
                    <a key={d} href={`${prefix}/${dep.qualifiedId}`} onClick={navClick(`${prefix}/${dep.qualifiedId}`)} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/5 text-sm text-[#d4d4d4] hover:text-[#52c7e8] hover:bg-white/10 transition-colors">
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.172 13.828a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.102 1.101" /></svg>
                      {d}
                    </a>
                  );
                })}
              </div>
            </div>
          )}
          {treeModules.length > 0 && (
            <div className="section-panel">
              <h3>{t.fileTree}</h3>
              <div className="max-h-60 overflow-y-auto text-sm">
                <FileTree modules={treeModules} />
              </div>
            </div>
          )}
        </div>
        <div className="space-y-4">
          {skill.aliases.length > 0 && (
            <div className="section-panel">
              <h3>{t.aliases}</h3>
              <div className="flex flex-wrap gap-2">
                {skill.aliases.map(a => <span key={a} className="px-2.5 py-1 rounded-full bg-white/5 text-sm text-[#8a8a8a]">{a}</span>)}
              </div>
            </div>
          )}
          <div className="section-panel">
            <div className="flex items-center justify-between mb-3">
              <h3 className="mb-0">{t.knowledgeGraph}</h3>
              <div className="flex gap-1 bg-white/5 rounded-md p-0.5">
                <button onClick={() => setGraphMode('files')} className={`px-2.5 py-1 rounded text-xs transition-colors ${graphMode === 'files' ? 'bg-[#52c7e8]/20 text-[#52c7e8]' : 'text-[#8a8a8a] hover:text-[#d4d4d4]'}`}>{t.fileGraph}</button>
                <button onClick={() => setGraphMode('knowledge')} className={`px-2.5 py-1 rounded text-xs transition-colors ${graphMode === 'knowledge' ? 'bg-[#52c7e8]/20 text-[#52c7e8]' : 'text-[#8a8a8a] hover:text-[#d4d4d4]'}`}>{t.knowledgeMap}</button>
              </div>
            </div>
            <p className="text-sm text-[#8a8a8a] mb-3">
              {graphMode === 'files'
                ? `${treeModules.length} file${treeModules.length !== 1 ? 's' : ''} in this skill`
                : knowledgeData
                  ? `${knowledgeData.nodes.length} ${t.nodes} · ${knowledgeData.edges.length} ${t.edges}`
                  : 'Parsed from TTL ontology data'}
            </p>
            <button onClick={openGraph} className="w-full flex items-center justify-center gap-2 py-3.5 rounded-lg bg-[#52c7e8]/[0.06] border border-[#52c7e8]/20 hover:bg-[#52c7e8]/[0.12] hover:border-[#52c7e8]/30 transition-all group cursor-pointer">
              <svg className="w-5 h-5 text-[#52c7e8] group-hover:scale-110 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z" /></svg>
              <span className="text-sm font-medium text-[#52c7e8] group-hover:text-[#f5f5f5] transition-colors">{t.openGraph}</span>
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

// ─── File Tree ────────────────────────────────────────────

function FileTree({ modules }: { modules: string[] }) {
  const tree = useMemo(() => {
    const root: any = {};
    for (const m of modules) {
      const parts = m.split('/');
      let node = root;
      for (let i = 0; i < parts.length; i++) {
        const p = parts[i];
        if (i === parts.length - 1) { node[p] = node[p] || { __file: true }; }
        else { node[p] = node[p] || {}; node = node[p]; }
      }
    }
    return root;
  }, [modules]);

  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const renderNode = (node: any, path: string = '', depth: number = 0): JSX.Element[] => {
    const entries = Object.entries(node).sort(([aName, a]: [string, any], [bName, b]: [string, any]) => {
      const aDir = !a.__file, bDir = !b.__file;
      if (aDir !== bDir) return aDir ? -1 : 1;
      return aName.localeCompare(bName);
    });
    const elements: JSX.Element[] = [];
    for (const [name, val] of entries) {
      const fullPath = path ? `${path}/${name}` : name;
      if ((val as any).__file) {
        const isOnto = name === 'ontoskill.ttl';
        elements.push(
          <div key={fullPath} className="flex items-center gap-2 py-0.5" style={{ paddingLeft: `${depth * 1.25}rem` }}>
            <svg className="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
            <span className={`font-mono text-xs ${isOnto ? 'text-[#52c7e8]' : 'text-[#8a8a8a]'}`}>{name}</span>
          </div>
        );
      } else {
        const isExpanded = expanded.has(fullPath);
        elements.push(
          <div key={fullPath}>
            <div
              className="flex items-center gap-1.5 py-0.5 cursor-pointer hover:text-[#52c7e8] select-none"
              style={{ paddingLeft: `${depth * 1.25}rem` }}
              onClick={() => setExpanded(prev => { const next = new Set(prev); next.has(fullPath) ? next.delete(fullPath) : next.add(fullPath); return next; })}
            >
              <svg className={`w-3.5 h-3.5 shrink-0 transition-transform ${isExpanded ? 'rotate-90' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
              <svg className="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" /></svg>
              <span className="font-mono text-xs">{name}/</span>
            </div>
            {isExpanded && renderNode(val, fullPath, depth + 1)}
          </div>
        );
      }
    }
    return elements;
  };

  return <div className="text-[#d4d4d4]">{renderNode(tree)}</div>;
}
