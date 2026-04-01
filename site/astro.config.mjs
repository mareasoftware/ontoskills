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
      head: [
        {
          tag: 'meta',
          attrs: { property: 'og:image', content: 'https://ontoskills.sh/og-image.png' }
        },
        {
          tag: 'meta',
          attrs: { name: 'twitter:image', content: 'https://ontoskills.sh/og-image.png' }
        }
      ],
      components: {
        PageTitle: './src/components/CustomPageTitle.astro',
      },
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
    }),
    tailwind(),
  ],
  output: 'static',
  site: 'https://ontoskills.sh',
});
