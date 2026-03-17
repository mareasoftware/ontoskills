import { defineConfig } from 'astro/config';
import tailwind from '@astrojs/tailwind';
import starlight from '@astrojs/starlight';

export default defineConfig({
  prefetch: {
    prefetchAll: true,
    defaultStrategy: 'hover'
  },
  integrations: [
    starlight({
      title: 'OntoClaw',
      description: 'Neuro-symbolic skill compiler for the Agentic Web',
      logo: {
        src: './src/assets/ontoclaw-logo.png',
        replacesTitle: false,
      },
      favicon: '/ontoclaw-logo.png',
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
  site: 'https://ontoclaw.marea.software',
});
