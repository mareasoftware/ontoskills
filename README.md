<p align="center">
  <img src="assets/ontoskills-banner.png" alt="OntoSkills: Neuro-Symbolic Skill Compiler" width="100%">
</p>

<h1 align="center">
  <a href="https://ontoskills.sh" style="text-decoration: none; color: inherit; display: flex; align-items: center; justify-content: center; gap: 10px;">
    <img src="assets/ontoskills-logo.png" alt="OntoSkills Logo Inline" height="40px" style="display: block;">
    <span>OntoSkills</span>
  </a>
</h1>

<p align="center">
  <b>🇬🇧 English</b> • <a href="README_zh.md">🇨🇳 中文</a>
</p>

<p align="center">
  <strong>The <span style="color:#e91e63">deterministic</span> enterprise AI agent platform.</strong>
</p>

<p align="center">
  Neuro-symbolic architecture for the Agentic Web — <span style="color:#00bf63;font-weight:bold">OntoCore</span> • <span style="color:#2196F3;font-weight:bold">OntoMCP</span> • <span style="color:#9333EA;font-weight:bold">OntoStore</span> • <span style="color:#faa338;font-weight:bold">OntoMemory</span>
</p>

<p align="center">
  <a href="https://ontoskills.sh/docs/overview/">Overview</a> •
  <a href="https://ontoskills.sh/docs/getting-started/">Getting Started</a> •
  <a href="https://ontoskills.sh/docs/roadmap/">Roadmap</a> •
  <a href="PHILOSOPHY.md">Philosophy</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue?style=for-the-badge&logo=python" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/node.js-18%2B-green?style=for-the-badge&logo=node.js" alt="Node.js 18+">
  <img src="https://img.shields.io/badge/OWL%202-RDF%2FTurtle-green?style=for-the-badge&logo=w3c" alt="OWL 2 RDF/Turtle">
  <img src="https://img.shields.io/badge/SHACL-Validation-purple?style=for-the-badge&logo=graphql" alt="SHACL Validation">
  <a href="#license">
    <img src="https://img.shields.io/badge/license-MIT-orange?style=for-the-badge" alt="MIT License">
  </a>
</p>

---

## What is OntoSkills?

OntoSkills transforms natural language skill definitions into **validated OWL 2 ontologies** — queryable knowledge graphs that enable deterministic reasoning for AI agents.

**The problem:** LLMs read skills probabilistically. Same query, different results. Long skill files burn tokens and confuse smaller models.

**The solution:** Compile skills to ontologies. Query with SPARQL. Get exact answers, every time.

```mermaid
flowchart LR
    CORE["OntoCore<br/>━━━━━━━━━━<br/>SKILL.md → .ttl<br/>LLM + SHACL"] -->|"compiles"| CENTER["OntoSkills<br/>━━━━━━━━━━<br/>OWL 2 Ontologies<br/>.ttl artifacts"]
    CENTER -->|"loads"| MCP["OntoMCP<br/>━━━━━━━━━━<br/>Rust SPARQL<br/>runtime graph"]
    MCP <-->|"queries"| AGENT["AI Agent<br/>━━━━━━━━━━<br/>Deterministic<br/>reasoning"]
    AGENT -->|"remembers"| MEMORY["OntoMemory<br/>━━━━━━━━━━<br/>Runtime memory<br/>graph-aware nodes"]
    MEMORY -->|"backfills"| MCP
    MCP -->|"visualizes"| GRAPH["OntoGraph<br/>━━━━━━━━━━<br/>Local 3D viewer<br/>memory editor"]

    style CORE fill:#e91e63,stroke:#2a2a3e,color:#f0f0f5
    style CENTER fill:#abf9cc,stroke:#2a2a3e,color:#0d0d14
    style MCP fill:#92eff4,stroke:#2a2a3e,color:#0d0d14
    style MEMORY fill:#faa338,stroke:#2a2a3e,color:#0d0d14
    style GRAPH fill:#26c7bd,stroke:#2a2a3e,color:#0d0d14
    style AGENT fill:#6dc9ee,stroke:#2a2a3e,color:#0d0d14
```

---

## Why OntoSkills?

| Problem | Solution |
|---------|----------|
| LLMs interpret text differently each time | SPARQL returns exact answers |
| 50+ skill files = context overflow | Query only what's needed |
| No verifiable structure for relationships | OWL 2 formal semantics |
| Small models can't read complex skills | Democratized intelligence via graph queries |

**For 100 skills:** ~500KB text scan → ~1KB query

[→ Read the full philosophy](PHILOSOPHY.md)

---

## Quick Start

```bash
# Install the MCP runtime and bootstrap your client
npx ontoskills install mcp --claude

# Or install the Python compiler separately
pip install ontocore
ontocore compile
```

[→ Full installation guide](https://ontoskills.sh/docs/getting-started/)

---

## Components

| Component | Language | Description |
|-----------|----------|-------------|
| **OntoCore** | Python | Neuro-symbolic compiler: SKILL.md → OWL 2 ontology |
| **OntoMCP** | Rust | MCP server with sub-ms SPARQL queries, runtime memory APIs, and OntoGraph |
| **OntoStore** | GitHub | Versioned skill registry |
| **OntoMemory** | Rust/RDF | Persistent project/global memory as graph-aware `KnowledgeNode` data |
| **OntoGraph** | Rust/Web | Local 3D viewer and editor for skills, states, memories, intents, topics, and relationships |
| **CLI** | Node.js | One-command installer (`npx ontoskills`) |

---

## Runtime Memories

OntoMemory stores remembered project and global knowledge as editable graph nodes, not loose text notes. Memories are `oc:Memory` nodes and subclasses of `oc:KnowledgeNode`, so agents can retrieve them through the same runtime graph used for compiled skills.

- Memories can link directly to skills, intents, topic clusters, and other memories.
- `depends_on_memory` represents operational chains where one memory relies on another.
- `supersedes_memory` records corrections and newer versions.
- `related_to_memory` captures thematic similarity without implying sequence.
- Topic clustering is deterministic and local in v1; embeddings are optional for skill discovery, not required for memory clustering.
- `recluster` backfills saved memories by recalculating topic clusters and generic memory links.

OntoGraph is the local graph UI for inspecting that runtime graph. It shows skills, knowledge nodes, states, memories, intents, and topics, and includes a full memory editor with incoming/outgoing relationships, memory chains, and topic clusters.

---

## Documentation

- **[Overview](https://ontoskills.sh/docs/overview/)** — What is OntoSkills and why it matters
- **[Getting Started](https://ontoskills.sh/docs/getting-started/)** — Installation and first steps
- **[Architecture](https://ontoskills.sh/docs/architecture/)** — How the system works
- **[OntoMemory](https://ontoskills.sh/docs/ontomemory/)** — Persistent runtime memory and graph relationships
- **[Knowledge Extraction](https://ontoskills.sh/docs/knowledge-extraction/)** — Extracting value from skills
- **[OntoStore](https://ontoskills.sh/ontostore/)** — Browse and install skills
- **[Roadmap](https://ontoskills.sh/docs/roadmap/)** — Development phases

---

## <a id="license"></a>License

MIT License — see [LICENSE](LICENSE) for details.

*© 2026 [MareaSW](https://ontoskills.sh)*
