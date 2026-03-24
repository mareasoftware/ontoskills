import { defineConfig } from 'astro/config';
import tailwind from '@astrojs/tailwind';
import starlight from '@astrojs/starlight';
import sitemap from '@astrojs/sitemap';
import mermaid from 'astro-mermaid';

export default defineConfig({
  prefetch: {
    prefetchAll: true,
    defaultStrategy: 'hover'
  },
  integrations: [
    sitemap(),
    mermaid({
      theme: 'dark'
    }),
    starlight({
      title: 'OntoSkills',
      description: 'Registry-backed skills, MCP runtime, and compiler for the Agentic Web',
      logo: {
        src: './src/assets/ontoskills-logo.png',
        replacesTitle: false,
      },
      favicon: '/ontoskills-logo.png',
      disable404Route: true,
      customCss: ['./src/styles/starlight.css'],
      defaultLocale: 'root',
      locales: {
        root: {
          label: 'English',
          lang: 'en',
        },
        zh: {
          label: '中文',
          lang: 'zh-CN',
        },
      },
      sidebar: [
        { label: 'Overview', slug: 'overview' },
        { label: 'Getting Started', slug: 'getting-started' },
        { label: 'CLI', slug: 'cli' },
        { label: 'Marketplace', slug: 'marketplace' },
        { label: 'Compiler', slug: 'compiler' },
        { label: 'Skill Authoring', slug: 'authoring' },
        { label: 'Architecture', slug: 'architecture' },
        { label: 'Knowledge Extraction', slug: 'knowledge-extraction' },
        { label: 'Semantic Discovery', slug: 'semantic-discovery' },
        { label: 'Store', slug: 'store' },
        { label: 'MCP Runtime', slug: 'mcp' },
        { label: 'Claude Code', slug: 'claude-code-mcp' },
        { label: 'Codex', slug: 'codex-mcp' },
        { label: 'Troubleshooting', slug: 'troubleshooting' },
        { label: 'Roadmap', slug: 'roadmap' },
      ],
    }),
    tailwind(),
  ],
  output: 'static',
  site: 'https://ontoskills.marea.software',
});
