<h1 align="center">
  <a href="https://ontoskills.sh/ontostore/" style="text-decoration: none; color: inherit; display: flex; align-items: center; justify-content: center; gap: 10px;">
    <span>OntoStore</span>
  </a>
</h1>

<p align="center">
  <b>The official skill registry for OntoSkills.</b>
</p>

<p align="center">
  Browse, install, and publish <strong>validated OWL 2 skill packages</strong> for deterministic AI agent behavior.
</p>

<p align="center">
  <a href="https://ontoskills.sh/docs/store/">Documentation</a> &bull;
  <a href="https://ontoskills.sh/ontostore/">Browse Skills</a> &bull;
  <a href="#publishing-a-package">Publish</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/packages-16-blue?style=for-the-badge" alt="16 Packages">
  <img src="https://img.shields.io/badge/skills-409-green?style=for-the-badge" alt="409 Skills">
  <img src="https://img.shields.io/badge/format-OWL%202%20RDF%2FTurtle-green?style=for-the-badge&logo=w3c" alt="OWL 2">
  <img src="https://img.shields.io/badge/trust-verified%20%2B%20community-purple?style=for-the-badge" alt="Trust Tiers">
  <a href="#license">
    <img src="https://img.shields.io/badge/license-MIT-orange?style=for-the-badge" alt="MIT License">
  </a>
</p>

---

## What is OntoStore?

OntoStore is the **versioned skill registry** at the heart of the OntoSkills ecosystem. It hosts pre-compiled OWL 2 ontology packages that AI agents query via SPARQL for deterministic, verifiable behavior.

Every package contains `.ttl` artifacts validated against the OntoSkills SHACL constitution — no probabilistic interpretation, no ambiguity.

```
ontoskills install obra/superpowers          # Install a package
ontoskills install obra/superpowers --with-embeddings  # With semantic search files
ontoskills install anthropics                # Install all from an author
```

---

## Available Packages

| Author | Package | Skills | Category |
|--------|---------|--------|----------|
| anthropics | [claude-office-skills](packages/anthropics/claude-office-skills/) | 137 | Office & productivity |
| anthropics | [knowledge-work-plugins](packages/anthropics/knowledge-work-plugins/) | 113 | Knowledge management |
| anthropics | [financial-services-plugin](packages/anthropics/financial-services-plugin/) | 27 | Finance & compliance |
| anthropics | [claude-plugin-official](packages/anthropics/claude-plugin-official/) | 19 | Plugin development |
| anthropics | [claude-code](packages/anthropics/claude-code/) | 10 | Code assistance |
| coreyhaines31 | [marketingskills](packages/coreyhaines31/marketingskills/) | 34 | Marketing |
| pbakaus | [impeccable](packages/pbakaus/impeccable/) | 21 | Quality & testing |
| coinbase | [agentic-wallet-skills](packages/coinbase/agentic-wallet-skills/) | 9 | Blockchain & wallets |
| n8n-io | [n8n](packages/n8n-io/n8n/) | 10 | Workflow automation |
| obra | [superpowers](packages/obra/superpowers/) | 14 | Developer tooling |
| nextlevel-builder | [ui-ux-pro-max-skill](packages/nextlevel-builder/ui-ux-pro-max-skill/) | 7 | UI/UX design |
| kotlin | [kotlin-agent-skills](packages/kotlin/kotlin-agent-skills/) | 4 | Kotlin development |
| remotion-dev | [skills](packages/remotion-dev/skills/) | 1 | Video creation |
| vercel-labs | [vercel-react-best-practices](packages/vercel-labs/vercel-react-best-practices/) | 1 | React development |
| vercel-labs | [agent-browser](packages/vercel-labs/agent-browser/) | 1 | Browser automation |
| mareasw | [greeting](packages/mareasw/greeting/) | 1 | Demo / hello world |

---

## Trust Tiers

Every package declares a trust tier that affects search ranking and visibility:

| Tier | Multiplier | Description |
|------|------------|-------------|
| `official` | 1.2x | Maintained by the OntoSkills team |
| `verified` | 1.0x | Reviewed and validated from known vendors |
| `community` | 0.8x | Community-contributed, use at your own discretion |

---

## Registry Structure

```
ontostore/
├── index.json                         # Registry index (packages list + embedding model)
├── embeddings/
│   └── tokenizer.json                 # Shared tokenizer for semantic search
├── packages/
│   ├── anthropics/
│   │   ├── claude-code/
│   │   │   ├── package.json           # Package manifest
│   │   │   └── <skill>/
│   │   │       ├── ontoskill.ttl      # Compiled OWL 2 ontology
│   │   │       └── intents.json       # Pre-computed embeddings (optional)
│   │   └── ...
│   ├── obra/
│   │   └── superpowers/
│   │       └── ...
│   └── ...
└── README.md
```

### `index.json`

The registry index lists all available packages and the embedding model metadata:

```json
{
  "embedding_model": {
    "model_name": "sentence-transformers/all-MiniLM-L6-v2",
    "dimension": 384,
    "model_file": "model.onnx",
    "tokenizer_file": "tokenizer.json"
  },
  "packages": [
    {
      "package_id": "obra/superpowers",
      "trust_tier": "verified",
      "source_kind": "ontology",
      "manifest_path": "packages/obra/superpowers/package.json"
    }
  ]
}
```

### `package.json` (per-package manifest)

Each package has a manifest declaring its skills, modules, and metadata:

```json
{
  "package_id": "obra/superpowers",
  "version": "0.11.0",
  "trust_tier": "verified",
  "source_kind": "ontology",
  "modules": ["tdd/ontoskill.ttl", "brainstorming/ontoskill.ttl"],
  "skills": [
    {
      "id": "tdd",
      "path": "tdd/ontoskill.ttl",
      "default_enabled": true,
      "aliases": ["test-driven-development"],
      "intents": ["write tests before code", "practice TDD"]
    }
  ],
  "embedding_files": ["tdd/intents.json", "brainstorming/intents.json"]
}
```

---

## Installing Packages

### From the CLI

```bash
# Install a single package
ontoskills install obra/superpowers

# Install with semantic search embeddings
ontoskills install obra/superpowers --with-embeddings

# Install all packages from an author
ontoskills install anthropics

# Enable/disable specific skills
ontoskills enable obra/superpowers tdd brainstorming
ontoskills disable obra/superpowers tdd
```

### Adding a Registry Source

```bash
ontoskills registry add-source official https://ontoskills.sh/ontostore/index.json
```

---

## Publishing a Package

### 1. Compile your skills

```bash
ontocore compile -i skills/ -o ontoskills/
```

### 2. Create a `package.json`

Place it in your skill directory alongside the compiled `.ttl` files. See the [package spec](https://ontoskills.sh/docs/store/) for the full schema.

### 3. Submit a PR

Fork this repository, add your package under `packages/<author>/<package>/`, update `index.json`, and open a pull request. Packages are validated against the OntoSkills SHACL constitution before merge.

**Requirements:**
- All `.ttl` files must pass SHACL validation
- `package.json` must conform to the package manifest schema
- Skill IDs must be unique across the registry
- Trust tier will be set to `community` by default; `verified` requires review

---

## Semantic Search

OntoStore ships optional pre-computed embeddings for semantic skill discovery. To use them:

1. Install with `--with-embeddings` to download per-skill `intents.json` files
2. The MCP server scans these files at startup for semantic matching
3. BM25 keyword search is always available as fallback

Embeddings use `sentence-transformers/all-MiniLM-L6-v2` (384-dim, L2-normalized).

---

## Related

- **[OntoSkills](https://ontoskills.sh)** — The platform
- **[OntoCore](https://ontoskills.sh/docs/ontocore/)** — The compiler
- **[OntoMCP](https://ontoskills.sh/docs/mcp/)** — The MCP runtime
- **[CLI Reference](https://ontoskills.sh/docs/cli/)** — Install commands

---

## <a id="license"></a>License

MIT License — see [LICENSE](../LICENSE) for details.

&copy; 2026 [MareaSW](https://ontoskills.sh)
