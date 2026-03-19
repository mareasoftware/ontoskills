# OntoSkills Site

Website and documentation for OntoSkills — the deterministic AI agent platform.

## Tech Stack

| Technology | Purpose |
|------------|---------|
| [Astro 5](https://astro.build/) | Static site generator |
| [Starlight](https://starlight.astro.build/) | Documentation framework |
| [Tailwind CSS](https://tailwindcss.com/) | Utility-first styling |
| [Pagefind](https://pagefind.app/) | Static search |

## Commands

```bash
npm install      # Install dependencies
npm run dev        # Start dev server at localhost:4321
npm run build     # Build to ./dist/
npm run preview   # Preview production build
```

## Project Structure

```
site/
├── public/              # Static assets
├── src/
│   ├── components/   # UI components
│   ├── content/       # Documentation (symlinked from ../../docs/)
│   ├── layouts/       # Page layouts
│   └── styles/        # Global styles
└── astro.config.mjs   # Astro configuration
```

## Documentation

Docs are symlinked from `docs/` to `src/content/docs/` for Starlight. Edit in `docs/`, not here.

## Deployment

Built for static hosting (Vercel, Netlify, Cloudflare Pages).

## License

© 2026 [Marea Software](https://marea.software)
