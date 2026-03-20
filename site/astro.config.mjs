import { defineConfig } from 'astro/config';
import tailwind from '@astrojs/tailwind';
import starlight from '@astrojs/starlight';
import sitemap from '@astrojs/sitemap';

export default defineConfig({
  prefetch: {
    prefetchAll: true,
    defaultStrategy: 'hover'
  },
  integrations: [
    sitemap(),
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
      head: [
        {
          tag: 'script',
          attrs: { src: 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js' }
        },
        {
          tag: 'script',
          attrs: { type: 'module' },
          content: `mermaid.initialize({ startOnLoad: true, theme: 'dark' });`
        },
      ],
      sidebar: [
        { label: 'Overview', slug: 'overview' },
        { label: 'Getting Started', slug: 'getting-started' },
        { label: 'Architecture', slug: 'architecture' },
        { label: 'Knowledge Extraction', slug: 'knowledge-extraction' },
        { label: 'Registry', slug: 'registry' },
        { label: 'MCP Runtime', slug: 'mcp' },
        { label: 'Claude Code', slug: 'mcp-claude-code' },
        { label: 'Codex', slug: 'mcp-codex' },
        { label: 'Roadmap', slug: 'roadmap' },
      ],
    }),
    tailwind(),
  ],
  output: 'static',
  site: 'https://ontoskills.marea.software',
});
