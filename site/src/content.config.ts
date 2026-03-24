import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { docsSchema } from '@astrojs/starlight/schema';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const docsDir = resolve(__dirname, './docs');

export const collections = {
  docs: defineCollection({
    loader: glob({ pattern: '**/*.md', base: docsDir }),
    schema: docsSchema(),
  }),
};
