# OntoSkills Site

Public site and documentation for [OntoSkills](https://ontoskills.sh) — ontology-powered skill resolution for AI agents.

## What's here

- **Landing page** (`/`) — redirects to `/en/`, marketing page with i18n support (English, Chinese)
- **Documentation** (`/en/`, `/zh/`) — Starlight-powered docs with bilingual content (e.g. `/en/overview/`)
- **OntoStore** (`/en/ontostore/`, `/zh/ontostore/`) — browsable skill registry

## Tech stack

| Technology | Purpose |
|------------|---------|
| [Astro 5](https://astro.build/) | Static site generator |
| [Starlight](https://starlight.astro.build/) | Documentation framework |
| [Tailwind CSS](https://tailwindcss.com/) | Utility-first styling |
| [Mermaid](https://mermaid.js.org/) | Diagrams in docs |
| [Vercel Analytics](https://vercel.com/analytics) | Traffic analytics |

## Commands

```bash
npm install
npm run dev      # dev server at localhost:4321
npm run build    # static build to dist/
npm run preview  # preview production build
```

Requires Node >= 22.

## Project structure

```
src/
├── components/
│   └── landing/        # Hero, Products, CTA, etc.
├── content/
│   └── docs/           # Starlight markdown docs (en/, zh/)
├── i18n/
│   ├── translations.ts  # Helpers + assembles per-lang dicts
│   ├── en.ts            # English strings
│   └── zh.ts            # Chinese strings
├── layouts/
│   └── LandingLayout.astro
├── pages/
│   ├── index.astro     # Redirects to /en/
│   ├── en/             # English Starlight pages
│   │   └── ontostore.astro
│   └── zh/             # Chinese Starlight pages
│       └── ontostore.astro
└── styles/
    └── starlight.css   # Custom Starlight theme overrides
```

## Deployment

Built for static hosting such as Vercel, Netlify, or Cloudflare Pages.

## License

(c) 2026 [Marea Software](https://marea.software)
