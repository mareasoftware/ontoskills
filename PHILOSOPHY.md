# OntoSkills Philosophy

<p>
  <b>🇬🇧 English</b> • <a href="PHILOSOPHY_zh.md">🇨🇳 中文</a>
</p>

## 0. Neuro-Symbolic AI Agent Platform

OntoSkills is not just a compiler — it's a **complete neuro-symbolic platform** for building deterministic, enterprise-grade AI agents. The ecosystem consists of five layered components:

```mermaid
flowchart LR
    CORE["OntoCore<br/>━━━━━━━━━━<br/>SKILL.md → .ttl<br/>LLM + SHACL"] -->|"compiles"| CENTER["OntoSkills<br/>━━━━━━━━━━<br/>OWL 2 Ontologies<br/>.ttl artifacts"]
    CENTER -->|"loads"| MCP["OntoMCP<br/>━━━━━━━━━━<br/>Rust SPARQL<br/>in-memory graph"]
    MCP <-->|"queries"| AGENT["OntoSkills<br/>━━━━━━━━━━<br/>Enterprise Agent<br/>deterministic"]
    CENTER <-->|"distributes"| STORE["OntoStore<br/>━━━━━━━━━━<br/>Registry<br/>versioning"]

    style CORE fill:#e91e63,stroke:#2a2a3e,color:#f0f0f5
    style CENTER fill:#abf9cc,stroke:#2a2a3e,color:#0d0d14
    style MCP fill:#92eff4,stroke:#2a2a3e,color:#0d0d14
    style AGENT fill:#6dc9ee,stroke:#2a2a3e,color:#0d0d14
    style STORE fill:#9763e1,stroke:#2a2a3e,color:#f0f0f5
```

### The Vision

**OntoSkills** is inspired by OpenClaw, Claude Code, and Cursor — but built for **enterprise** with a focus on:

- **Determinism**: OWL 2 Description Logics guarantee decidable reasoning
- **Speed**: Rust-based runtime (OntoMCP) for blazing-fast SPARQL queries
- **Reliability**: SHACL validation ensures ontological consistency
- **Modularity**: Plug-and-play skill ontologies

The key insight: **Skills are compiled artifacts, not interpreted documents.**

---

## 1. The Lifecycle: Source Code vs Artifact

OntoCore implements a **compile-time paradigm** for skills, separating human authoring from machine execution:

### Design Time (Source Code)

```mermaid
flowchart LR
    MD["Human writes<br/>SKILL.md<br/>━━━━━━━━━━<br/>Developer-friendly<br/>natural language"] -.->|"compiles to"| NOTE["Markdown = syntactic sugar<br/>for OWL 2<br/>━━━━━━━━━━<br/>RDF/Turtle output"]

    style MD fill:#6dc9ee,stroke:#2a2a3e,color:#0d0d14
    style NOTE fill:#9763e1,stroke:#2a2a3e,color:#f0f0f5
```

Why Markdown? Because writing raw Turtle by hand is a terrible developer experience.

OntoCore extracts **everything** into the TTL:
- Intents (`oc:resolvesIntent`)
- State transitions (`oc:requiresState`, `oc:yieldsState`, `oc:handlesFailure`)
- **Execution payload** (`oc:hasPayload` with `oc:executor` + `oc:code` or `oc:executionPath`)
- Dependencies and relations (`oc:dependsOn`, `oc:extends`, `oc:contradicts`)

### Runtime (Artifact)

```mermaid
flowchart LR
    AGENT["LLM Agent<br/>━━━━━━━━━━<br/>Queries skills<br/>via SPARQL"] <-->|"SELECT ?skill"| MCP["OntoMCP (Rust)<br/>━━━━━━━━━━<br/>In-memory graph<br/>blazing-fast"]
    MCP -->|"loads"| TTL[".ttl files<br/>━━━━━━━━━━<br/>Self-contained<br/>modular ontologies"]

    style AGENT fill:#6dc9ee,stroke:#2a2a3e,color:#0d0d14
    style MCP fill:#92eff4,stroke:#2a2a3e,color:#0d0d14
    style TTL fill:#9763e1,stroke:#2a2a3e,color:#f0f0f5
```

**SKILL.md files DO NOT EXIST in the agent's context.** The .ttl files are self-contained, modular, pluggable ontologies. All logic lives in RDF.

**The compiled TTL is the executable artifact. The Markdown is just source code that gets compiled away.**

This separation enables:
- **Human-friendly authoring** (Markdown during development)
- **Machine-optimal execution** (OWL 2 at runtime)
- **Modular deployment** (plug/unplug skill ontologies without touching source)

---

## 2. The Core Problem

Large Language Models are powerful but **non-deterministic**. The same prompt can yield different outputs across runs. When an agent must navigate dozens of skills, it faces:

### Context and Scale

- **Context rot**: Loading 50+ SKILL.md files consumes context window
- **Hallucination risk**: Information scattered across files is easily misremembered
- **No verifiable structure**: "Does skill A depend on skill B?" requires reading both files

### The Small Model Problem

This is where the problem becomes **critical**: smaller models (7B-14B parameters) are increasingly deployed for:

- **Edge computing**: On-device inference without cloud dependency
- **Cost reduction**: $0.001/1K tokens vs $0.015/1K tokens for frontier models
- **Privacy**: Sensitive data never leaves the local machine
- **Latency**: Sub-100ms response times for real-time applications

**But small models cannot load 50 skill files.** Consider:

| Model | Context Window | Practical Capacity |
|-------|---------------|-------------------|
| Claude Opus 4 | 200K tokens | ~100 skill files |
| Claude Sonnet | 200K tokens | ~100 skill files |
| Llama 3.1 8B | 128K tokens | ~60 skill files |
| Mistral 7B | 32K tokens | ~15 skill files |
| Phi-3 Mini | 4K tokens | ~2 skill files |

A 7B model can barely load a **single skill ecosystem** before running out of context. And even when context fits:

- **Comprehension degrades**: Small models struggle to extract structured relationships from unstructured text
- **Reasoning breaks**: "Which skills can handle state X?" requires multi-file reasoning that small models fail at
- **Consistency fails**: The same query about skill dependencies may return different answers across runs

### The Cost Spiral

For enterprises running agents at scale, token consumption directly impacts the bottom line:

| Scenario | Tokens | Cost per 1M queries (Opus 4.6) | Cost per 1M queries (Sonnet 4.6) |
|----------|--------|-------------------------------|--------------------------------|
| Load all 50 skills | ~300K | $2,500 | $1,500 |
| SPARQL query to ontology | ~1.5K | $17.50 | $10.50 |

*Pricing: Opus 4.6 ($5/MTok input, $25/MTok output), Sonnet 4.6 ($3/MTok input, $15/MTok output)*

The ontology approach reduces costs by **~150x** for Sonnet.

### The Retry Problem

Non-deterministic reasoning creates a hidden cost multiplier: **stupid retries**.

When an LLM agent interprets skill metadata, it makes unpredictable mistakes:

**Examples of wasteful retries:**
- **Wrong tool calls**: Agent calls `list_skills` instead of `find_skills_by_intent`
- **Scattershot approach**: Tries 3-4 different skills before finding one that works
- **Hallucinated capabilities**: "This skill can probably handle images" — when it cannot
- **Looping on understanding**: Re-reads skill descriptions trying to "get it"
- **Context overflow**: Loads entire skill file just to answer "what does this require?"

Each retry consumes the full context window. With 50+ skills, this adds up fast.

**With deterministic SPARQL:**
- Same input → same result (zero interpretation variance)
- Skill selection is **exact**, not probabilistic
- **No "thinking" overhead** — query returns answer directly
- **No hallucination** — the ontology is the single source of truth
- **Predictable costs** — you know exactly how many tokens each query costs

**Determinism isn't just about correctness — it's about eliminating waste.**

### The Consistency Gap

Even large models suffer from **inconsistent skill interpretation**:

- **Ambiguous language**: "This skill requires authentication" — is that a precondition or a feature?
- **Implicit relationships**: Skill A mentions "use Skill B for validation" — is that a dependency? An extension?
- **Scattered metadata**: Intent strings, state requirements, and execution hints are buried in prose

Without formal semantics, every LLM query about skills is a **gamble on interpretation**.

---

This is the **knowledge retrieval problem** in the age of LLMs — and OntoSkills solves it by making skills **queryable, not readable**.

---

## 3. The Ontological Solution

OntoSkills applies **Description Logics (DL)** — specifically the **$\mathcal{SROIQ}^{(D)}$** fragment underlying OWL 2 DL — to transform unstructured skill definitions into **formal, queryable knowledge graphs**.

### Why $\mathcal{SROIQ}^{(D)}$?

Each letter represents a capability that solves a specific problem in skill modeling:

| Feature | Capability | OntoSkills Example |
|---------|------------|------------------|
| **$\mathcal{S}$** | Transitive properties | `A extends B extends C` → A extends C automatically |
| **$\mathcal{R}$** | Complex role inclusions | `dependsOn` and `contradicts` are mutually exclusive |
| **$\mathcal{O}$** | Nominals (enumerated classes) | Define `EntryPoints = {create, import, init}` |
| **$\mathcal{I}$** | Inverse properties | `A dependsOn B` ↔ `B enables A` (auto-derived) |
| **$\mathcal{Q}$** | Cardinality restrictions | `ExecutableSkill` has exactly 1 `hasPayload` |
| **$\mathcal{D}$** | Datatypes | Strings, integers, booleans for literals |

**Decidability**: OWL 2 DL is decidable — reasoning algorithms terminate in finite time with correct answers. This contrasts with the open-ended nature of LLM reasoning.

---

## 4. Neuro-Symbolic Architecture

OntoSkills is **neuro-symbolic**: it combines neural and symbolic AI paradigms.

```mermaid
flowchart LR
    NEURAL["Neural Layer<br/>━━━━━━━━━━<br/>LLM Extraction<br/>Claude extracts<br/>structured knowledge<br/>(probabilistic)"] -->|"Pydantic"| SYMBOLIC["Symbolic Layer<br/>━━━━━━━━━━<br/>OWL 2 Ontology<br/>Formal semantics<br/>decidable reasoning<br/>(deterministic)"]
    SYMBOLIC -->|"serialize"| QUERY["Query Layer<br/>━━━━━━━━━━<br/>SPARQL Engine<br/>O(1) indexed lookup<br/>precise retrieval<br/>(deterministic)"]

    style NEURAL fill:#6dc9ee,stroke:#2a2a3e,color:#0d0d14
    style SYMBOLIC fill:#9763e1,stroke:#2a2a3e,color:#f0f0f5
    style QUERY fill:#abf9cc,stroke:#2a2a3e,color:#0d0d14
```

- **Neural**: Claude extracts structured knowledge from natural language (OntoCore)
- **Symbolic**: OWL 2 ontology stores knowledge with formal semantics (OntoSkills)
- **Query**: SPARQL provides precise, indexed retrieval (OntoMCP)

The neural layer handles ambiguity and interpretation. The symbolic layer ensures consistency and verifiability.

---

## 5. Democratizing Intelligence

A key ambition: **enable smaller models to reason about large skill ecosystems**.

Consider an agent with 100 skills:
- **Without ontology**: Must read 100 SKILL.md files (~500KB of text) to understand capabilities
- **With ontology**: Queries `SELECT ?skill WHERE { ?skill oc:resolvesIntent ?intent }` in milliseconds

This is especially valuable for:
- **Edge deployment**: Smaller models on local hardware
- **Cost reduction**: Fewer tokens processed per query
- **Reliability**: Deterministic answers, no hallucination about skill relationships

### Schema Exposure

Before querying, an LLM needs to know: **"What can I ask?"**

OntoSkills exposes the **TBox** (terminological box) — the schema of classes and properties — separately from the **ABox** (assertional box) of individual skills.

```mermaid
flowchart LR
    TBOX["TBox (Schema)<br/>━━━━━━━━━━<br/>What properties does<br/>oc:Skill have?<br/>→ oc:resolvesIntent<br/>→ oc:dependsOn<br/>→ oc:extends"] -->|"informs"| ABOX["ABox (Instances)<br/>━━━━━━━━━━<br/>Which skills resolve<br/>'create_pdf'?<br/>→ oc:pdf-generation<br/>→ oc:docx-to-pdf"]

    style TBOX fill:#9763e1,stroke:#2a2a3e,color:#f0f0f5
    style ABOX fill:#abf9cc,stroke:#2a2a3e,color:#0d0d14
```

This two-stage querying prevents "blind" questions and improves precision.

---

## 6. Performance Characteristics

| Operation | Text Files | OWL Ontology |
|-----------|------------|--------------|
| Find skill by intent | O(n) scan all files | O(1) indexed SPARQL |
| Check dependencies | Parse each file | Follow `oc:dependsOn` edges |
| Detect conflicts | Compare all pairs | `oc:contradicts` lookup |
| Transitive closure | Recursively scan | OWL reasoning (optional) |

For 100 skills with average 5KB each:
- **Text scan**: ~500KB to read
- **SPARQL query**: ~1KB index lookup

The gap widens with scale.

---

## 7. Schema-First Querying

Traditional skill systems require the LLM to "guess" what information exists. OntoSkills inverts this:

1. **First**: Query the TBox to understand available classes and properties
2. **Then**: Construct precise ABox queries with known predicates

Example TBox query:

```sparql
SELECT ?property ?range WHERE {
  ?property rdfs:domain oc:Skill .
  ?property rdfs:range ?range .
}
```

Returns: `oc:resolvesIntent → xsd:string`, `oc:dependsOn → oc:Skill`, etc.

This enables **informed querying** — the LLM knows the ontology's structure before asking questions.

---

## 8. Enterprise Focus

OntoSkills is designed for **production enterprise environments**:

### Determinism Over Flexibility

While other agents optimize for flexibility, OntoSkills optimizes for **predictable, reproducible behavior**:

- Same input → same skill selection (via SPARQL, not LLM judgment)
- Same dependencies → same execution order (via `oc:dependsOn` edges)
- Same states → same transitions (via `oc:requiresState` / `oc:yieldsState`)

### Security First

OntoCore implements **defense-in-depth**:
- Regex pattern matching for known attack vectors
- LLM review for ambiguous content
- SHACL validation prevents malformed ontologies
- No execution of unvalidated payloads

### Audit Trail

Every compiled skill carries:
- `oc:generatedBy` — which LLM model extracted it
- `oc:hash` — content hash for integrity verification
- `oc:provenance` — source file reference

---

## 9. Research Foundations

OntoSkills builds on decades of research in Knowledge Representation, Logical Reasoning, and modern AI:

**Description Logics & Reasoning**
* Baader, F., Calvanese, D., McGuinness, D., Nardi, D., & Patel-Schneider, P. (2003). *The Description Logic Handbook*. Cambridge University Press.
* Horrocks, I., Kutz, O., & Sattler, U. (2006). "The Even More Irresistible SROIQ". *Proceedings of KR-2006*. (The mathematical foundation of OWL 2).

**Ontologies & Validation (W3C)**
* W3C OWL 2 Web Ontology Language (2009). https://www.w3.org/TR/owl2-overview/
* Cuenca Grau, B., Horrocks, I., Motik, B., et al. (2008). "OWL 2: The next step for OWL". *Journal of Web Semantics*.
* Knublauch, H., & Kontokostas, D. (2017). "Shapes Constraint Language (SHACL)". *W3C Recommendation*.

**Knowledge Representation**
* Brachman, R., Levesque, H. (2004). *Knowledge Representation and Reasoning*. Morgan Kaufmann.
* Sowa, J. (2000). *Knowledge Representation: Logical, Philosophical, and Computational Foundations*. Brooks/Cole.

**Neuro-Symbolic AI & Semantic Web**
* d'Avila Garcez, A., Lamb, L. (2020). "Neurosymbolic AI: The 3rd Wave". *arXiv:2012.05876*.
* Pan, S., et al. (2024). "Unifying Large Language Models and Knowledge Graphs: A Roadmap". *IEEE TKDE*.
* Heath, T., Bizer, C. (2011). "Linked Data: Evolving the Web into a Global Data Space". *Synthesis Lectures on the Semantic Web*.
* SPARQL 1.1 Query Language (2013). https://www.w3.org/TR/sparql11-query/

*OntoSkills is the bridge: neural flexibility for extraction, symbolic rigor for storage, precise queries for retrieval.*
