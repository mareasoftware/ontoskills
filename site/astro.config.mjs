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
      description: 'OntoStore-backed skills, MCP runtime, and compiler for the Agentic Web',
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
        {
          label: 'Documentation',
          autogenerate: { directory: '.' },
        },
      ],
    }),
    tailwind(),
  ],
  output: 'static',
  site: 'https://ontoskills.sh',
});
