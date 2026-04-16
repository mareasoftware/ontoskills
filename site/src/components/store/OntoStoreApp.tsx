import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { OrbitControls, Text, Line } from '@react-three/drei';
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
      if (idSet.has(d)) edges.push({ source: s.skillId, target: d });
    }
  }
  return { nodes, edges };
}

function packageHasDeps(skillList: Skill[]) {
  const idSet = new Set(skillList.map(s => s.skillId));
  return skillList.some(s => s.dependsOn.some(d => idSet.has(d)));
}

function layoutForce3D(nodes: GraphNode[], edges: GraphEdge[]) {
  const positions: Record<string, { x: number; y: number; z: number }> = {};
  const n = nodes.length;
  if (!n) return positions;
  const R = Math.max(n * 1.8, 8);
  nodes.forEach((node, i) => {
    const phi = Math.acos(-1 + (2 * i) / n);
    const theta = Math.sqrt(n * Math.PI) * phi;
    positions[node.id] = {
      x: R * Math.cos(theta) * Math.sin(phi),
      y: R * Math.sin(theta) * Math.sin(phi),
      z: R * Math.cos(phi),
    };
  });
  const k = R * 1.2;
  for (let iter = 0; iter < 180; iter++) {
    const temp = 1 - iter / 180;
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const a = positions[nodes[i].id], b = positions[nodes[j].id];
        const dx = a.x - b.x, dy = a.y - b.y, dz = a.z - b.z;
        const dist = Math.max(Math.sqrt(dx * dx + dy * dy + dz * dz), 0.1);
        const force = (k * k) / dist;
        const fx = (dx / dist) * force * temp * 0.4;
        const fy = (dy / dist) * force * temp * 0.4;
        const fz = (dz / dist) * force * temp * 0.4;
        a.x += fx; a.y += fy; a.z += fz;
        b.x -= fx; b.y -= fy; b.z -= fz;
      }
    }
    for (const e of edges) {
      const s = positions[e.source], t = positions[e.target];
      if (!s || !t) continue;
      const dx = t.x - s.x, dy = t.y - s.y, dz = t.z - s.z;
      const dist = Math.max(Math.sqrt(dx * dx + dy * dy + dz * dz), 0.1);
      const force = (dist * dist) / k;
      const fx = (dx / dist) * force * temp * 0.2;
      const fy = (dy / dist) * force * temp * 0.2;
      const fz = (dz / dist) * force * temp * 0.2;
      s.x += fx; s.y += fy; s.z += fz;
      t.x -= fx; t.y -= fy; t.z -= fz;
    }
    for (const node of nodes) {
      const p = positions[node.id];
      p.x *= 0.98; p.y *= 0.98; p.z *= 0.98;
    }
  }
  return positions;
}

// ─── 3D Graph Components ──────────────────────────────────

function GraphNodeSphere({ node, position, onClick }: {
  node: GraphNode;
  position: [number, number, number];
  onClick: (qualifiedId: string) => void;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const [hovered, setHovered] = useState(false);
  const color = node.isHighlighted ? '#52c7e8'
    : node.category === 'productivity' ? '#85f496'
    : node.category === 'development' ? '#52c7e8'
    : '#9763e1';
  const radius = node.isHighlighted ? 1.4 : 0.9;

  useFrame(() => {
    if (meshRef.current) {
      meshRef.current.scale.setScalar(1);
    }
  });

  return (
    <group position={position}>
      {node.isHighlighted && (
        <mesh>
          <sphereGeometry args={[radius * 2.5, 32, 32]} />
          <meshBasicMaterial color={color} transparent opacity={0.08} />
        </mesh>
      )}
      <mesh
        ref={meshRef}
        onClick={(e) => { e.stopPropagation(); onClick(node.qualifiedId); }}
        onPointerOver={(e) => { e.stopPropagation(); setHovered(true); document.body.style.cursor = 'pointer'; }}
        onPointerOut={() => { setHovered(false); document.body.style.cursor = 'default'; }}
      >
        <sphereGeometry args={[radius, 32, 32]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={hovered ? 0.6 : node.isHighlighted ? 0.4 : 0.15}
          roughness={0.3}
          metalness={0.2}
          transparent
          opacity={0.9}
        />
      </mesh>
      <Text
        position={[0, -radius - 0.8, 0]}
        fontSize={0.55}
        color="#d4d4d4"
        anchorX="center"
        anchorY="top"
        font={undefined}
      >
        {node.label}
      </Text>
    </group>
  );
}

function GraphEdgeLine({ start, end }: { start: [number, number, number]; end: [number, number, number] }) {
  const mid: [number, number, number] = [
    (start[0] + end[0]) / 2,
    (start[1] + end[1]) / 2,
    (start[2] + end[2]) / 2,
  ];
  return (
    <Line
      points={[start, end]}
      color="white"
      lineWidth={1}
      transparent
      opacity={0.12}
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

function Scene({ nodes, edges, onNodeClick, autoRotate = true }: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  onNodeClick: (qualifiedId: string) => void;
  autoRotate?: boolean;
}) {
  const positions = useMemo(() => layoutForce3D(nodes, edges), [nodes, edges]);

  return (
    <>
      <ambientLight intensity={0.5} />
      <pointLight position={[20, 20, 20]} intensity={1.5} color="#52c7e8" />
      <pointLight position={[-20, -10, 15]} intensity={0.8} color="#85f496" />
      {autoRotate && <AutoRotate />}
      <OrbitControls
        enableDamping
        dampingFactor={0.08}
        autoRotate={false}
        minDistance={10}
        maxDistance={80}
      />
      {nodes.map(n => {
        const p = positions[n.id];
        if (!p) return null;
        return (
          <GraphNodeSphere
            key={n.id}
            node={n}
            position={[p.x, p.y, p.z]}
            onClick={onNodeClick}
          />
        );
      })}
      {edges.map((e, i) => {
        const s = positions[e.source], t = positions[e.target];
        if (!s || !t) return null;
        return <GraphEdgeLine key={i} start={[s.x, s.y, s.z]} end={[t.x, t.y, t.z]} />;
      })}
    </>
  );
}

function KnowledgeGraph3D({ nodes, edges, onNodeClick, height = 350 }: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  onNodeClick: (qualifiedId: string) => void;
  height?: number;
}) {
  if (!nodes.length) return null;
  return (
    <div style={{ width: '100%', height, borderRadius: '0.5rem', overflow: 'hidden' }}>
      <Canvas camera={{ position: [0, 0, 30], fov: 55 }} gl={{ alpha: true, antialias: true }}>
        <Scene nodes={nodes} edges={edges} onNodeClick={onNodeClick} />
      </Canvas>
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
    });
  };
  return (
    <button onClick={handleCopy} className="shrink-0 p-1.5 rounded hover:bg-white/5 opacity-40 hover:opacity-100 transition-opacity" title={t.copyToClipboard}>
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

  const [skills, setSkills] = useState<Skill[]>([]);
  const [packages, setPackages] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  // Routing
  const [viewMode, setViewMode] = useState<ViewMode>('store');
  const [authorId, setAuthorId] = useState('');
  const [pkgId, setPkgId] = useState('');
  const [skillId, setSkillId] = useState('');
  const [graphExpanded, setGraphExpanded] = useState(false);

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
      const path = window.location.pathname.replace(/\/$/, '');
      const storePath = path.replace(prefix, '').replace(/^\//, '');
      const segments = storePath ? storePath.split('/') : [];
      setGraphExpanded(false);
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

  if (loading) {
    return <div className="text-center py-20 text-[#8a8a8a]">{t.connecting}</div>;
  }

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
        {viewMode === 'store' && <StoreView skills={skills} filteredSkills={filteredSkills} meta={meta} t={t} prefix={prefix} navigate={navigate} searchQuery={searchQuery} setSearchQuery={setSearchQuery} filterAuthor={filterAuthor} setFilterAuthor={setFilterAuthor} filterCategory={filterCategory} setFilterCategory={setFilterCategory} filterTier={filterTier} setFilterTier={setFilterTier} filterSort={filterSort} setFilterSort={setFilterSort} visibleCount={visibleCount} setVisibleCount={setVisibleCount} lang={lang} />}
        {viewMode === 'author' && <AuthorView skills={skills} authorId={authorId} t={t} prefix={prefix} navigate={navigate} />}
        {viewMode === 'package' && <PackageView skills={skills} packages={packages} pkgId={pkgId} t={t} prefix={prefix} navigate={navigate} />}
        {viewMode === 'skill' && <SkillDetailView skills={skills} packages={packages} pkgId={pkgId} skillId={skillId} t={t} prefix={prefix} navigate={navigate} lang={lang} />}
      </div>
    </div>
  );
}

// ─── Store View ───────────────────────────────────────────

function StoreView({ skills, filteredSkills, meta, t, prefix, navigate, searchQuery, setSearchQuery, filterAuthor, setFilterAuthor, filterCategory, setFilterCategory, filterTier, setFilterTier, filterSort, setFilterSort, visibleCount, setVisibleCount, lang }: any) {
  const docsLink = lang === 'zh' ? '/zh/docs/getting-started/' : '/docs/getting-started/';
  const visible = filteredSkills.slice(0, visibleCount);
  const remaining = filteredSkills.length - visibleCount;

  return (
    <>
      <div className="mb-10">
        <h2 className="text-2xl sm:text-3xl font-bold text-[#f5f5f5] mb-2">{t.storeLabel}</h2>
        <p className="text-base text-[#d4d4d4]">{t.allSkills}</p>
      </div>

      {/* Get Started */}
      <div className="section-panel mb-8">
        <h3>{t.getStarted}</h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
          <div>
            <p className="text-sm text-[#f5f5f5] font-medium mb-2">{t.step1Title}</p>
            <p className="text-xs text-[#8a8a8a] mb-3">{t.step1Desc}</p>
            <InstallBar command={t.setupMcpCommand} t={t} id="gs1" />
          </div>
          <div>
            <p className="text-sm text-[#f5f5f5] font-medium mb-2">{t.step2Title}</p>
            <p className="text-xs text-[#8a8a8a] mb-3">{t.step2Desc}</p>
            <InstallBar command={t.setupSkillCommand} t={t} id="gs2" />
          </div>
          <div>
            <p className="text-sm text-[#f5f5f5] font-medium mb-2">{t.step3Title}</p>
            <p className="text-xs text-[#8a8a8a] mb-3">{t.step3Desc}</p>
            <div className="mt-4"><a href={docsLink} className="text-[#52c7e8] hover:underline text-sm">{t.setupDocs} →</a></div>
          </div>
        </div>
      </div>

      {/* Search + filters */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between mb-6">
        <div className="relative flex-1 sm:max-w-md">
          <svg className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-[#8a8a8a]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
          <input className="w-full bg-white/[0.04] border border-white/10 rounded-lg pl-10 pr-4 py-2.5 text-sm text-[#f5f5f5] outline-none placeholder:text-[#8a8a8a] focus:border-[#52c7e8]/50 transition-colors" type="search" placeholder={t.searchPlaceholder} value={searchQuery} onChange={e => setSearchQuery(e.target.value)} />
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <select value={filterAuthor} onChange={e => setFilterAuthor(e.target.value)} className="store-filter-select" aria-label={t.author}>
            <option value="">{t.allAuthors}</option>
            {meta.authors.map((a: string) => <option key={a} value={a}>{a}</option>)}
          </select>
          <select value={filterCategory} onChange={e => setFilterCategory(e.target.value)} className="store-filter-select" aria-label={t.category}>
            <option value="">{t.allCategories}</option>
            {meta.categories.map((c: string) => <option key={c} value={c}>{c}</option>)}
          </select>
          <select value={filterTier} onChange={e => setFilterTier(e.target.value)} className="store-filter-select" aria-label={t.trustTier}>
            <option value="">{t.allTiers}</option>
            {meta.trustTiers.map((tier: string) => <option key={tier} value={tier}>{tier === 'official' ? t.official : tier === 'verified' ? t.verified : tier === 'community' ? t.community : tier}</option>)}
          </select>
          <select value={filterSort} onChange={e => setFilterSort(e.target.value)} className="store-filter-select" aria-label={t.sort}>
            <option value="az">{t.sortAZ}</option>
            <option value="za">{t.sortZA}</option>
          </select>
          <span className="text-sm text-[#8a8a8a] ml-2">{filteredSkills.length} {filteredSkills.length === 1 ? t.skill_one : t.skill_other}</span>
        </div>
      </div>

      {/* Grid */}
      {!filteredSkills.length ? (
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
    <article
      className="skill-card rounded-xl border border-white/[0.07] bg-white/[0.02] p-5 flex flex-col gap-3 cursor-pointer hover:border-[#52c7e8]/30 hover:bg-[#52c7e8]/[0.04] hover:-translate-y-0.5 hover:shadow-[0_6px_24px_rgba(0,0,0,0.3)] transition-all duration-200"
      onClick={() => navigate(`${prefix}/${skill.qualifiedId}`)}
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
    </article>
  );
}

// ─── Author View ──────────────────────────────────────────

function AuthorView({ skills, authorId, t, prefix, navigate }: { skills: Skill[]; authorId: string; t: typeof translations.en; prefix: string; navigate: (href: string) => void }) {
  const authorSkills = skills.filter(s => s.author === authorId);
  const pkgMap: Record<string, Skill[]> = {};
  authorSkills.forEach(s => { pkgMap[s.packageId] = pkgMap[s.packageId] || []; pkgMap[s.packageId].push(s); });

  return (
    <>
      <div className="breadcrumb flex items-center gap-2 text-sm mb-8">
        <a href={prefix} onClick={e => { e.preventDefault(); navigate(prefix); }} className="text-[#8a8a8a] hover:text-[#52c7e8] transition-colors">{t.storeLabel}</a>
        <span className="text-[#8a8a8a]">/</span>
        <span className="text-[#f5f5f5] font-medium">{authorId}</span>
      </div>
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 mb-10">
        <div>
          <h2 className="text-2xl sm:text-3xl font-bold text-[#f5f5f5] mb-2">{authorId}</h2>
          <p className="text-sm text-[#8a8a8a]">{authorSkills.length} {t.totalSkills} · {Object.keys(pkgMap).length} {t.packages.toLowerCase()}</p>
        </div>
        <InstallBar command={`npx ontoskills install ${authorId}/<package>`} t={t} id="authInstall" />
      </div>
      {Object.entries(pkgMap).map(([pid, pkgSkills]) => {
        const tier = pkgSkills[0]?.trustTier || 'verified';
        const ver = pkgSkills[0]?.version || '';
        const pkgName = pid.split('/').slice(1).join('/');
        const cats = [...new Set(pkgSkills.map(s => s.category).filter(Boolean))];
        return (
          <div key={pid} className="mb-8">
            <div className="flex items-center gap-3 mb-3">
              <h3 className="text-xl font-semibold text-[#f5f5f5] cursor-pointer hover:text-[#52c7e8] transition-colors" onClick={() => navigate(`${prefix}/${pid}`)}>{pkgName}</h3>
              <TrustBadge tier={tier} t={t} />
              {ver && <span className="text-xs text-[#8a8a8a]">v{ver}</span>}
              <span className="text-xs text-[#8a8a8a]">{pkgSkills.length} {t.skills.toLowerCase()}</span>
            </div>
            <p className="text-sm text-[#8a8a8a] mb-4">{cats.join(', ') || '—'}</p>
          </div>
        );
      })}
    </>
  );
}

// ─── Package View ─────────────────────────────────────────

function PackageView({ skills, packages, pkgId, t, prefix, navigate }: { skills: Skill[]; packages: any[]; pkgId: string; t: typeof translations.en; prefix: string; navigate: (href: string) => void }) {
  const pkgSkills = skills.filter(s => s.packageId === pkgId);
  const author = pkgId.split('/')[0];
  const pkgName = pkgId.split('/').slice(1).join('/');
  const tier = pkgSkills[0]?.trustTier || 'verified';
  const ver = pkgSkills[0]?.version || '';
  const rawPkg = packages.find(p => p.package_id === pkgId);
  const modules: string[] = rawPkg?.modules || [];
  const hasDeps = packageHasDeps(pkgSkills);
  const graphData = useMemo(() => hasDeps ? buildGraphData(pkgSkills) : null, [pkgSkills, hasDeps]);

  const handleGraphNodeClick = useCallback((qualifiedId: string) => {
    navigate(`${prefix}/${qualifiedId}`);
  }, [navigate, prefix]);

  return (
    <>
      <div className="breadcrumb flex items-center gap-2 text-sm mb-8">
        <a href={prefix} onClick={e => { e.preventDefault(); navigate(prefix); }} className="text-[#8a8a8a] hover:text-[#52c7e8] transition-colors">{t.storeLabel}</a>
        <span className="text-[#8a8a8a]">/</span>
        <a href={`${prefix}/${author}`} onClick={e => { e.preventDefault(); navigate(`${prefix}/${author}`); }} className="text-[#8a8a8a] hover:text-[#52c7e8] transition-colors">{author}</a>
        <span className="text-[#8a8a8a]">/</span>
        <span className="text-[#f5f5f5] font-medium">{pkgName}</span>
      </div>
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 mb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <h2 className="text-2xl sm:text-3xl font-bold text-[#f5f5f5]">{pkgName}</h2>
            <TrustBadge tier={tier} t={t} />
            {ver && <span className="text-sm text-[#8a8a8a]">v{ver}</span>}
          </div>
          <code className="text-sm text-[#8a8a8a] font-mono">{pkgId}</code>
          <p className="text-sm text-[#8a8a8a] mt-1">{pkgSkills.length} {t.skills.toLowerCase()}</p>
        </div>
        <InstallBar command={`npx ontoskills install ${pkgId}`} t={t} id="pkgInstall" />
      </div>
      {hasDeps && graphData && (
        <div className="section-panel mb-6">
          <h3>{t.knowledgeGraph}</h3>
          <KnowledgeGraph3D nodes={graphData.nodes} edges={graphData.edges} onNodeClick={handleGraphNodeClick} height={350} />
        </div>
      )}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {pkgSkills.map(s => <SkillCard key={s.qualifiedId} skill={s} t={t} prefix={prefix} navigate={navigate} />)}
          </div>
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
  const [graphExpanded, setGraphExpanded] = useState(false);

  if (!skill) {
    return <div className="text-center py-20"><p className="text-[#d4d4d4] text-lg">{t.noMatch}</p></div>;
  }

  const author = pkgId.split('/')[0];
  const pkgName = pkgId.split('/').slice(1).join('/');
  const rawPkg = packages.find(p => p.package_id === pkgId);
  const modules: string[] = rawPkg?.modules || [];
  const skillModules = modules.filter(m => m.startsWith(skillId + '/') || m === `${skillId}/ontoskill.ttl`);
  const treeModules = skillModules.length ? skillModules : modules.filter(m => m.startsWith(skillId));

  const pkgSkills = skills.filter(s => s.packageId === pkgId);
  const hasPkgDeps = packageHasDeps(pkgSkills);

  // Graph data: skill view or expanded package view
  const graphData = useMemo(() => {
    if (graphExpanded) return buildGraphData(pkgSkills, skillId);
    const depIds = new Set([skillId, ...skill.dependsOn]);
    const graphSkills = pkgSkills.filter(s => depIds.has(s.skillId));
    return buildGraphData(graphSkills, skillId);
  }, [graphExpanded, pkgSkills, skillId, skill.dependsOn]);

  const graphSkillsCount = useMemo(() => {
    const depIds = new Set([skillId, ...skill.dependsOn]);
    return pkgSkills.filter(s => depIds.has(s.skillId)).length;
  }, [pkgSkills, skillId, skill.dependsOn]);

  const handleGraphNodeClick = useCallback((qualifiedId: string) => {
    navigate(`${prefix}/${qualifiedId}`);
  }, [navigate, prefix]);

  return (
    <>
      <div className="breadcrumb flex items-center gap-2 text-sm mb-8">
        <a href={prefix} onClick={e => { e.preventDefault(); navigate(prefix); }} className="text-[#8a8a8a] hover:text-[#52c7e8] transition-colors">{t.storeLabel}</a>
        <span className="text-[#8a8a8a]">/</span>
        <a href={`${prefix}/${author}`} onClick={e => { e.preventDefault(); navigate(`${prefix}/${author}`); }} className="text-[#8a8a8a] hover:text-[#52c7e8] transition-colors">{author}</a>
        <span className="text-[#8a8a8a]">/</span>
        <a href={`${prefix}/${pkgId}`} onClick={e => { e.preventDefault(); navigate(`${prefix}/${pkgId}`); }} className="text-[#8a8a8a] hover:text-[#52c7e8] transition-colors">{pkgName}</a>
        <span className="text-[#8a8a8a]">/</span>
        <span className="text-[#f5f5f5] font-medium">{skillId}</span>
      </div>
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 mb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <h2 className="text-2xl sm:text-3xl font-bold text-[#f5f5f5]">{skillId}</h2>
            <TrustBadge tier={skill.trustTier} t={t} />
            {skill.version && <span className="text-sm text-[#8a8a8a]">v{skill.version}</span>}
            {skill.category && <span className="px-2.5 py-1 rounded-full bg-white/5 text-xs text-[#8a8a8a]">{skill.category}</span>}
          </div>
          <code className="text-sm text-[#8a8a8a] font-mono">{skill.qualifiedId}</code>
          <p className="mt-3 text-base text-[#d4d4d4] leading-relaxed">{skill.description}</p>
        </div>
        <InstallBar command={skill.installCommand} t={t} id="skillInstall" />
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
                  const dep = skills.find(s => s.skillId === d);
                  const href = dep ? `${prefix}/${dep.qualifiedId}` : '#';
                  return (
                    <a key={d} href={href} onClick={e => { if (dep) { e.preventDefault(); navigate(`${prefix}/${dep.qualifiedId}`); } }} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/5 text-sm text-[#d4d4d4] hover:text-[#52c7e8] hover:bg-white/10 transition-colors">
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
              <h3>Aliases</h3>
              <div className="flex flex-wrap gap-2">
                {skill.aliases.map(a => <span key={a} className="px-2.5 py-1 rounded-full bg-white/5 text-sm text-[#8a8a8a]">{a}</span>)}
              </div>
            </div>
          )}
          <div className="section-panel">
            <h3>{t.knowledgeGraph}</h3>
            {graphSkillsCount > 1 ? (
              <>
                <KnowledgeGraph3D nodes={graphData.nodes} edges={graphData.edges} onNodeClick={handleGraphNodeClick} height={300} />
                {hasPkgDeps && (
                  <div className="mt-2">
                    <button onClick={() => setGraphExpanded(!graphExpanded)} className="text-xs text-[#52c7e8] hover:underline">
                      {graphExpanded ? t.backToSkillGraph : `${t.viewPackageGraph} →`}
                    </button>
                  </div>
                )}
              </>
            ) : (
              <div className="flex items-center justify-center py-8">
                <div className="w-10 h-10 rounded-full bg-[#52c7e8]/20 border border-[#52c7e8]" />
                <span className="ml-3 text-sm text-[#8a8a8a]">{t.noDeps}</span>
              </div>
            )}
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
    const entries = Object.entries(node).sort(([_a, a]: [string, any], [_b, b]: [string, any]) => {
      const aDir = !a.__file, bDir = !b.__file;
      if (aDir !== bDir) return aDir ? -1 : 1;
      return 0;
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
