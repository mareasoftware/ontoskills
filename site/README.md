# OntoSkills Site

Public site and documentation shell for OntoSkills.

The site presents the current product surface:
- `ontoskills` as the user-facing CLI
- `ontomcp` as the runtime server
- `ontocore` as the optional compiler
- `OntoSkills Registry` as the official compiled-skill registry

## Tech Stack

| Technology | Purpose |
|------------|---------|
| [Astro 5](https://astro.build/) | Static site generator |
| [Starlight](https://starlight.astro.build/) | Documentation framework |
| [Tailwind CSS](https://tailwindcss.com/) | Utility-first styling |
| [Pagefind](https://pagefind.app/) | Static search |

## Commands

```bash
npm install
npm run dev
npm run build
npm run preview
```

## Project Structure

```
site/
├── public/              # Static assets
├── src/
│   ├── components/      # Landing-page UI
│   ├── content/         # Starlight docs source (symlink to ../../docs)
│   ├── layouts/         # Page layouts
│   └── styles/          # Global styles
└── astro.config.mjs     # Astro configuration
```

## Documentation

The docs are rendered through Starlight and loaded from the repository-level `docs/` directory via `site/src/content/docs`.

## Deployment

Built for static hosting such as Vercel, Netlify, or Cloudflare Pages.

## License

© 2026 [Marea Software](https://marea.software)
