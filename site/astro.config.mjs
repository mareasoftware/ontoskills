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
      description: 'Neuro-symbolic skill core for the Agentic Web',
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
        { label: 'Roadmap', slug: 'roadmap' },
      ],
    }),
    tailwind(),
  ],
  output: 'static',
  site: 'https://ontoskills.marea.software',
});
