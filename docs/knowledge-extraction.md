---
title: Knowledge Extraction
description: How OntoSkills extracts structured knowledge from skills
---

## From SKILL.md to Ontology

A skill is not just code — it's **structured knowledge**. OntoCore extracts this knowledge and compiles it into a queryable ontology.

---

## What Gets Extracted

Every skill is compiled with:

| Element | Property | Description |
|---------|----------|-------------|
| **Identity** | `oc:nature`, `oc:genus`, `oc:differentia` | "A is a B that C" definition |
| **Intents** | `oc:resolvesIntent` | What user intentions this skill resolves |
| **Requirements** | `oc:hasRequirement` | Dependencies (EnvVar, Tool, Hardware, API, Knowledge) |
| **Knowledge Nodes** | `oc:impartsKnowledge` | Epistemic knowledge (8-12 per skill) |
| **State Transitions** | `oc:requiresState`, `oc:yieldsState`, `oc:handlesFailure` | Preconditions, outcomes, error handling |
| **Execution Payload** | `oc:hasPayload` | Optional code to execute |
| **Provenance** | `oc:generatedBy` | Attestation (which LLM compiled it) |

---

## Knowledge Nodes

The heart of knowledge extraction. Each skill imparts 8-12 **Knowledge Nodes** — structured epistemic rules.

### The 10 Knowledge Node Types

| Type | Description | Example |
|------|-------------|---------|
| **Heuristic** | Rule of thumb | "Prefer streaming for files >100MB" |
| **AntiPattern** | What to avoid | "Don't read entire file into memory" |
| **PreFlightCheck** | Verify before execution | "Check disk space before download" |
| **RecoveryTactic** | How to recover from failure | "Retry with exponential backoff" |
| **OptimizationHint** | Performance guidance | "Cache compiled regex patterns" |
| **ContextualConstraint** | When this applies | "Only works on Unix systems" |
| **ImplementationDetail** | Technical specifics | "Uses libcurl for HTTP" |
| **ExternalDependency** | Required tools/libs | "Requires Python 3.10+" |
| **FailureMode** | How it can fail | "Timeout on slow networks" |
| **SuccessMetric** | How to measure success | "Process completes in <5s" |

### Node Structure

Each Knowledge Node has:

- `directiveContent` — The actual rule or insight
- `appliesToContext` — When this applies
- `hasRationale` — Why this rule exists
- `severityLevel` — How important (critical, warning, info)

---

## Modular Ontology Architecture

### The Single Skill as Module

Each compiled skill is a **self-contained `.ttl` file**:

```
ontoskills/
├── ontoskills-core.ttl      # Core TBox (shared)
├── index.ttl                # Manifest with owl:imports
├── pdf/
│   └── ontoskill.ttl        # PDF skill module
├── markdown/
│   └── ontoskill.ttl        # Markdown skill module
└── email/
    └── ontoskill.ttl        # Email skill module
```

### Pluggable Knowledge

- **Add** a skill → Drop a `.ttl` file
- **Remove** a skill → Delete the `.ttl` file
- **Update** a skill → Replace the `.ttl` file

The global ontology grows by **addition**, not modification.

---

## Querying the Knowledge

### Find Skills by Intent

```sparql
SELECT ?skill WHERE {
  ?skill oc:resolvesIntent "create_pdf"
}
```

### Get Knowledge Nodes for a Skill

```sparql
SELECT ?content ?type WHERE {
  <skill:pdf> oc:impartsKnowledge ?node .
  ?node oc:directiveContent ?content .
  ?node a ?type .
}
```

### Find Anti-Patterns Across All Skills

```sparql
SELECT ?skill ?content WHERE {
  ?skill oc:impartsKnowledge ?node .
  ?node a oc:AntiPattern .
  ?node oc:directiveContent ?content .
}
```

---

## The Value Proposition

| Before (Reading Files) | After (Ontology Query) |
|------------------------|------------------------|
| Parse 50 SKILL.md files | Single SPARQL query |
| ~500KB text scan | ~1KB query |
| Non-deterministic | Exact results |
| Context overflow | Query what you need |
| LLM interprets | Graph returns |

**Knowledge becomes queryable. Intelligence becomes democratized.**
