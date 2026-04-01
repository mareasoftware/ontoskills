export default {
  hero: {
    badgeTagline: '基于本体的技能解析',
    badgeTerms: ['OWL 2 本体', 'Rust MCP', '确定性查询'],
    headline: '技能是查出来的，',
    headlineAccent: '不是猜出来的。',
    subheadline: '用确定性的本体查询替代概率性的技能发现。零歧义，零令牌浪费。',
    cta: '浏览 OntoStore',
    secondaryCta: '开始使用',
    stats: [
      { value: 'O(1)', label: '查找' },
      { value: '100%', label: '确定性' },
      { value: 'OWL 2 DL', label: '推理' },
    ],
  },
  problemSolution: {
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
  products: {
    title: '产品',
    subtitle: '三个组件。一个确定性管道。',
    items: [
      {
        name: 'OntoCore',
        description: '编译器。将领域知识转换为 OWL 2 本体。',
        features: ['知识提取', 'OWL 2 DL 合规', 'SPARQL 端点'],
        link: '/zh/docs/ontocore/',
      },
      {
        name: 'OntoStore',
        description: '注册表。浏览、发布和发现本体技能。',
        features: ['技能发现', '版本控制', 'CLI 集成'],
        link: '/zh/ontostore/',
      },
      {
        name: 'OntoMCP',
        description: '运行时。MCP 服务器，将代理连接到本体知识。',
        features: ['Claude Code 就绪', 'SPARQL 查询', '技能执行'],
        link: '/zh/docs/mcp/',
      },
    ],
  },
  roadmap: {
    badge: '即将推出',
    title: 'OntoClaw',
    subtitle: '第一个原生本体 AI 代理',
    description: '神经符号架构。本体知识是原生的 — OntoSkills 不需要 MCP 桥接。',
  },
  cta: {
    headline: '准备好让你的代理变得确定性了吗？',
    command: 'npx ontoskills install mcp',
    installMCP: '安装 OntoMCP',
    primaryButton: '开始使用',
    secondaryButton: '浏览 OntoStore',
  },
  header: {
    ontostore: 'OntoStore',
    howItWorks: '工作原理',
    docs: '文档',
    getStarted: '开始使用',
  },
  footer: {
    product: '产品',
    resources: '资源',
    community: '社区',
    roadmap: '路线图',
    documentation: '文档',
    gettingStarted: '开始使用',
    cliReference: 'CLI 参考',
    architecture: '架构',
    copyright: '© 2026 OntoSkills. 保留所有权利。',
  },
  howItWorks: {
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
  ontostore: {
    title: 'OntoStore — 浏览本体技能',
    headline: '浏览本体技能。复制安装命令。',
    subtitle: '通过意图、名称或描述查找技能。直接复制安装命令。',
    storeLabel: '商店',
  },
} as const;
