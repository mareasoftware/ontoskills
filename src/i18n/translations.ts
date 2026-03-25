// Translation dictionaries for landing pages

export const languages = {
  en: 'English',
  zh: '中文',
} as const;

export type Lang = keyof typeof languages;

export const defaultLang: Lang = 'en';

// Hero translations
const hero = {
  en: {
    badge: 'OWL 2 Ontologies • Rust MCP • Deterministic Queries',
    headline: 'Your agent shouldn\'t have to read to know what to do.',
    subheadline: 'Replace probabilistic skill discovery with deterministic ontological queries. Zero ambiguity. Zero tokens wasted on parsing.',
    cta: 'Browse OntoStore',
    secondaryCta: 'Get Started',
    stats: [
      { value: 'O(1)', label: 'Lookup' },
      { value: '100%', label: 'Deterministic' },
      { value: 'OWL 2 DL', label: 'Reasoning' },
    ],
  },
  zh: {
    badge: 'OWL 2 本体 • Rust MCP • 确定性查询',
    headline: '你的代理不应该通过阅读来知道该做什么。',
    subheadline: '用确定性的本体查询替代概率性的技能发现。零歧义。零令牌浪费。',
    cta: '浏览 OntoStore',
    secondaryCta: '开始使用',
    stats: [
      { value: 'O(1)', label: '查找' },
      { value: '100%', label: '确定性' },
      { value: 'OWL 2 DL', label: '推理' },
    ],
  },
};

// Problem/Solution translations
const problemSolution = {
  en: {
    problem: {
      label: 'The Problem',
      headline: 'LLMs waste tokens guessing',
      subheadline: 'Every time your agent uses a skill, it burns through a 4-step pipeline that\'s slow, expensive, and unreliable.',
      steps: [
        { name: 'Read', desc: 'Parse docs' },
        { name: 'Understand', desc: 'Build context' },
        { name: 'Reason', desc: 'Decide action' },
        { name: 'Execute', desc: 'Run skill' },
      ],
      painPoints: [
        { title: 'Token Waste', desc: 'Large models burn thousands of tokens just parsing documentation files.', icon: 'warning' },
        { title: 'Inconsistency', desc: 'Same query, different results. Every. Single. Time.', icon: 'shuffle' },
        { title: 'Confusion', desc: 'Complex skills overwhelm smaller models with ambiguity.', icon: 'confusion' },
        { title: 'No Guarantees', desc: 'LLMs interpret text probabilistically. Errors are inevitable.', icon: 'warning2' },
      ],
    },
    solution: {
      label: 'The Solution',
      headline: 'Skip the guesswork. Query. Execute.',
      subheadline: 'OntoSkills eliminates reading and understanding. An OWL 2 reasoner handles the heavy lifting — deterministically.',
      codeExample: {
        agent: '"I need to create a PDF"',
        sparql: 'SELECT ?skill WHERE { ?skill resolvesIntent "create_pdf" }',
        result: 'pdf-generator',
        action: 'Execute skill payload',
      },
      tagline: 'No reading. No guessing. Just query → execute.',
    },
  },
  zh: {
    problem: {
      label: '问题',
      headline: 'LLM 浪费令牌在猜测',
      subheadline: '每次你的代理使用技能时，它都要经历一个缓慢、昂贵且不可靠的4步流程。',
      steps: [
        { name: '阅读', desc: '解析文档' },
        { name: '理解', desc: '构建上下文' },
        { name: '推理', desc: '决定行动' },
        { name: '执行', desc: '运行技能' },
      ],
      painPoints: [
        { title: '令牌浪费', desc: '大型模型仅解析文档文件就消耗数千个令牌。', icon: 'warning' },
        { title: '不一致性', desc: '相同的查询，不同的结果。每次都是如此。', icon: 'shuffle' },
        { title: '困惑', desc: '复杂的技能会让较小的模型感到困惑。', icon: 'confusion' },
        { title: '无保证', desc: 'LLM 概率性地解释文本。错误是不可避免的。', icon: 'warning2' },
      ],
    },
    solution: {
      label: '解决方案',
      headline: '跳过猜测。查询。执行。',
      subheadline: 'OntoSkills 消除了阅读和理解。OWL 2 推理器以确定性方式处理繁重工作。',
      codeExample: {
        agent: '"我需要创建一个 PDF"',
        sparql: 'SELECT ?skill WHERE { ?skill resolvesIntent "create_pdf" }',
        result: 'pdf-generator',
        action: '执行技能负载',
      },
      tagline: '无需阅读。无需猜测。只需 查询 → 执行。',
    },
  },
};

// Products translations
const products = {
  en: {
    title: 'Products',
    subtitle: 'Three components. One deterministic pipeline.',
    items: [
      {
        name: 'OntoCore',
        description: 'The compiler. Transform domain knowledge into OWL 2 ontologies.',
        features: ['Knowledge extraction', 'OWL 2 DL compliance', 'SPARQL endpoint'],
        link: '/en/ontocore/',
      },
      {
        name: 'OntoStore',
        description: 'The registry. Browse, publish, and discover ontological skills.',
        features: ['Intent-based search', 'Version control', 'CLI integration'],
        link: '/ontostore/',
      },
      {
        name: 'OntoMCP',
        description: 'The runtime. MCP server that bridges agents to ontological knowledge.',
        features: ['Claude Code ready', 'SPARQL queries', 'Skill execution'],
        link: '/en/mcp/',
      },
    ],
  },
  zh: {
    title: '产品',
    subtitle: '三个组件。一个确定性管道。',
    items: [
      {
        name: 'OntoCore',
        description: '编译器。将领域知识转换为 OWL 2 本体。',
        features: ['知识提取', 'OWL 2 DL 合规', 'SPARQL 端点'],
        link: '/zh/ontocore/',
      },
      {
        name: 'OntoStore',
        description: '注册表。浏览、发布和发现本体技能。',
        features: ['基于意图的搜索', '版本控制', 'CLI 集成'],
        link: '/ontostore/',
      },
      {
        name: 'OntoMCP',
        description: '运行时。MCP 服务器，将代理连接到本体知识。',
        features: ['Claude Code 就绪', 'SPARQL 查询', '技能执行'],
        link: '/zh/mcp/',
      },
    ],
  },
};

// Roadmap translations
const roadmap = {
  en: {
    badge: 'Coming Soon',
    title: 'OntoClaw',
    subtitle: 'The first natively ontological AI agent',
    description: 'Neuro-symbolic architecture. Ontological knowledge is native — no MCP bridge needed for OntoSkills.',
  },
  zh: {
    badge: '即将推出',
    title: 'OntoClaw',
    subtitle: '第一个原生本体 AI 代理',
    description: '神经符号架构。本体知识是原生的 — OntoSkills 不需要 MCP 桥接。',
  },
};

// CTA translations
const cta = {
  en: {
    headline: 'Ready to make your agent deterministic?',
    command: 'npx ontoskills install mcp',
    primaryButton: 'Get Started',
    secondaryButton: 'Browse OntoStore',
  },
  zh: {
    headline: '准备好让你的代理变得确定性了吗？',
    command: 'npx ontoskills install mcp',
    primaryButton: '开始使用',
    secondaryButton: '浏览 OntoStore',
  },
};

// Landing CTA (different from above)
const landingCta = {
  en: {
    headline: 'Ready to make your agent deterministic?',
    command: 'npx ontoskills install mcp',
    primaryButton: 'Get Started',
    secondaryButton: 'Browse OntoStore',
  },
  zh: {
    headline: '准备好让你的代理变得确定性了吗？',
    command: 'npx ontoskills install mcp',
    primaryButton: '开始使用',
    secondaryButton: '浏览 OntoStore',
  },
};

// Header translations
const header = {
  en: {
    ontostore: 'OntoStore',
    howItWorks: 'How it Works',
    docs: 'Docs',
    getStarted: 'Get Started',
  },
  zh: {
    ontostore: 'OntoStore',
    howItWorks: '工作原理',
    docs: '文档',
    getStarted: '开始使用',
  },
};

// Footer translations
const footer = {
  en: {
    product: 'Product',
    resources: 'Resources',
    community: 'Community',
    roadmap: 'Roadmap',
    documentation: 'Documentation',
    gettingStarted: 'Getting Started',
    cliReference: 'CLI Reference',
    architecture: 'Architecture',
    copyright: '© 2026 OntoSkills. Built with Astro + Starlight.',
  },
  zh: {
    product: '产品',
    resources: '资源',
    community: '社区',
    roadmap: '路线图',
    documentation: '文档',
    gettingStarted: '开始使用',
    cliReference: 'CLI 参考',
    architecture: '架构',
    copyright: '© 2026 OntoSkills. 基于 Astro + Starlight 构建。',
  },
};

// How it Works translations
const howItWorks = {
  en: {
    title: 'How it Works',
    subtitle: 'Four steps to deterministic skill discovery',
    steps: [
      {
        title: '1. Define',
        description: 'Create an ontology that captures your domain knowledge — intents, skills, and their relationships.',
        code: '# ontoskills init\nontoskills init my-project\n\n# Define your ontology\n# ontology.ttl',
      },
      {
        title: '2. Compile',
        description: 'OntoCore compiles your ontology into an OWL 2 DL knowledge base.',
        code: '# Compile the ontology\nontoskills compile ontology.ttl\n\n# Output: knowledge-base.owl',
      },
      {
        title: '3. Query',
        description: 'Use SPARQL to query for skills based on intents. The reasoner handles inference.',
        code: 'SELECT ?skill WHERE {\n  ?skill oc:resolvesIntent "create_pdf" .\n  ?skill oc:hasCapability "text_to_pdf" .\n}',
      },
      {
        title: '4. Execute',
        description: 'The MCP server returns the skill payload. Your agent executes it deterministically.',
        code: '// Skill payload returned\n{\n  "name": "pdf-generator",\n  "command": "pandoc",\n  "args": ["input.md", "-o", "output.pdf"]\n}',
      },
    ],
    cta: {
      headline: 'Ready to get started?',
      button: 'Read the Docs',
    },
  },
  zh: {
    title: '工作原理',
    subtitle: '确定性技能发现的四个步骤',
    steps: [
      {
        title: '1. 定义',
        description: '创建一个捕获领域知识的本体 — 意图、技能及其关系。',
        code: '# ontoskills init\nontoskills init my-project\n\n# 定义你的本体\n# ontology.ttl',
      },
      {
        title: '2. 编译',
        description: 'OntoCore 将你的本体编译为 OWL 2 DL 知识库。',
        code: '# 编译本体\nontoskills compile ontology.ttl\n\n# 输出: knowledge-base.owl',
      },
      {
        title: '3. 查询',
        description: '使用 SPARQL 根据意图查询技能。推理器处理推理。',
        code: 'SELECT ?skill WHERE {\n  ?skill oc:resolvesIntent "create_pdf" .\n  ?skill oc:hasCapability "text_to_pdf" .\n}',
      },
      {
        title: '4. 执行',
        description: 'MCP 服务器返回技能负载。你的代理以确定性方式执行它。',
        code: '// 返回的技能负载\n{\n  "name": "pdf-generator",\n  "command": "pandoc",\n  "args": ["input.md", "-o", "output.pdf"]\n}',
      },
    ],
    cta: {
      headline: '准备好开始了吗？',
      button: '阅读文档',
    },
  },
};

// OntoStore translations
const ontostore = {
  en: {
    title: 'OntoStore — Browse Ontological Skills',
    headline: 'Browse ontological skills. Copy install commands.',
    subtitle: 'Find skills by intent, name, or description. Copy install commands directly.',
  },
  zh: {
    title: 'OntoStore — 浏览本体技能',
    headline: '浏览本体技能。复制安装命令。',
    subtitle: '通过意图、名称或描述查找技能。直接复制安装命令。',
  },
};

// Export all translations
export const translations = {
  hero,
  problemSolution,
  products,
  roadmap,
  cta,
  header,
  footer,
  howItWorks,
  ontostore,
} as const;

// Helper function to get translations for a language
export function getTranslations(lang: Lang) {
  return {
    lang,
    hero: translations.hero[lang],
    problemSolution: translations.problemSolution[lang],
    products: translations.products[lang],
    roadmap: translations.roadmap[lang],
    cta: translations.cta[lang],
    header: translations.header[lang],
    footer: translations.footer[lang],
    howItWorks: translations.howItWorks[lang],
    ontostore: translations.ontostore[lang],
  };
}

// Helper to get language from URL path
export function getLangFromUrl(url: string): Lang {
  const [, lang] = url.split('/');
  if (lang in translations.hero) return lang as Lang;
  return defaultLang;
}

// Helper to get localized path
export function getLocalizedPath(path: string, lang: Lang): string {
  if (path.startsWith('/')) {
    return `/${lang}${path === '/' ? '' : path}`;
  }
  return path;
}
