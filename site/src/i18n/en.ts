export default {
  hero: {
    badgeTagline: 'Ontology-Powered Skill Resolution',
    badgeTerms: ['OWL 2 ontologies', 'Rust MCP', 'Deterministic queries'],
    headline: 'Skills your agent can look up,',
    headlineAccent: 'not guess.',
    subheadline: 'Deterministic ontological queries replace probabilistic skill discovery. Zero ambiguity, zero tokens wasted.',
    cta: 'Browse OntoStore',
    secondaryCta: 'Get started',
    stats: [
      { value: 'O(1)', label: 'Lookup' },
      { value: '100%', label: 'Deterministic' },
      { value: 'OWL 2 DL', label: 'Reasoning' },
    ],
  },
  problemSolution: {
    problem: {
      label: 'The problem',
      headline: 'LLMs waste tokens guessing',
      subheadline: 'Every time your agent uses a skill, it burns through a 4-step pipeline that\'s slow, expensive, and unreliable.',
      steps: [
        { name: 'Read', desc: 'Parse docs' },
        { name: 'Understand', desc: 'Build context' },
        { name: 'Reason', desc: 'Decide action' },
        { name: 'Execute', desc: 'Run skill' },
      ],
      painPoints: [
        { title: 'Token waste', desc: 'Large models burn thousands of tokens just parsing documentation files.', icon: 'warning' },
        { title: 'Inconsistency', desc: 'Same query, different results. Every. Single. Time.', icon: 'shuffle' },
        { title: 'Confusion', desc: 'Complex skills overwhelm smaller models with ambiguity.', icon: 'confusion' },
        { title: 'No guarantees', desc: 'LLMs interpret text probabilistically. Errors are inevitable.', icon: 'warning2' },
      ],
    },
    solution: {
      label: 'The solution',
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
  products: {
    title: 'Products',
    subtitle: 'Three components. One deterministic pipeline.',
    items: [
      {
        name: 'OntoCore',
        description: 'The compiler. Transform domain knowledge into OWL 2 ontologies.',
        features: ['Knowledge extraction', 'OWL 2 DL compliance', 'SPARQL endpoint'],
        link: '/docs/ontocore/',
      },
      {
        name: 'OntoStore',
        description: 'The registry. Browse, publish, and discover ontological skills.',
        features: ['Skill discovery', 'Version control', 'CLI integration'],
        link: '/ontostore/',
      },
      {
        name: 'OntoMCP',
        description: 'The runtime. MCP server that bridges agents to ontological knowledge.',
        features: ['Claude Code ready', 'SPARQL queries', 'Skill execution'],
        link: '/docs/mcp/',
      },
    ],
  },
  roadmap: {
    badge: 'Coming soon',
    title: 'OntoClaw',
    subtitle: 'The first natively ontological AI agent',
    description: 'Neuro-symbolic architecture. Ontological knowledge is native — no MCP bridge needed for OntoSkills.',
  },
  cta: {
    headline: 'Ready to make your agent deterministic?',
    command: 'npx ontoskills install mcp',
    installMCP: 'Install OntoMCP',
    primaryButton: 'Get started',
    secondaryButton: 'Browse OntoStore',
  },
  header: {
    ontostore: 'OntoStore',
    howItWorks: 'How it works',
    docs: 'Docs',
    getStarted: 'Get started',
  },
  footer: {
    product: 'Product',
    resources: 'Resources',
    community: 'Community',
    roadmap: 'Roadmap',
    documentation: 'Documentation',
    gettingStarted: 'Getting started',
    cliReference: 'CLI reference',
    architecture: 'Architecture',
    copyright: '© 2026 OntoSkills. All rights reserved.',
  },
  howItWorks: {
    title: 'How it works',
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
  ontostore: {
    title: 'OntoStore — Browse ontological skills',
    headline: 'Browse ontological skills. Copy install commands.',
    subtitle: 'Find skills by intent, name, or description. Copy install commands directly.',
    storeLabel: 'Store',
  },
} as const;
