---
title: Knowledge Extraction
description: How OntoCore extracts structured knowledge from skills
sidebar:
  order: 9
---

A skill is not just code — it's **structured knowledge**. OntoCore extracts this knowledge and compiles it into a queryable ontology.

> **Note:** Embedding generation is an optional step in the compilation pipeline. Install `ontocore[embeddings]` to produce per-skill vector embeddings for semantic intent search. When not installed, embedding generation is skipped with a warning — BM25 keyword search remains available in the MCP runtime.

---

## What gets extracted

Every skill is compiled with:

| Element | Property | Description |
|----------|-----------|-------------|
| **Identity** | `oc:nature`, `oc:genus`, `oc:differentia` | "A is a B that C" definition |
| **Intents** | `oc:resolvesIntent` | What user intentions this skill resolves |
| **Requirements** | `oc:hasRequirement` | Dependencies (EnvVar, Tool, Hardware, API, Knowledge) |
| **Knowledge Nodes** | `oc:impartsKnowledge` | Epistemic + operational knowledge (8-15 per skill) |
| **State Transitions** | `oc:requiresState`, `oc:yieldsState`, `oc:handlesFailure` | Preconditions, outcomes, error handling |
| **Execution Payload** | `oc:hasPayload` | Optional code to execute |
| **Provenance** | `oc:generatedBy` | Attestation (which LLM compiled it) (optional) |

### Components

| Element | Property | Description |
|----------|-----------|-------------|
| **Reference Files** | `oc:hasReferenceFile` | Supporting docs with `purpose` (api-reference, examples, guide, domain-specific, other) |
| **Workflows** | `oc:hasWorkflow` | Multi-step processes with `hasStep` dependencies |
| **Examples** | `oc:hasExample` | Input/output pairs for pattern matching |

---

## Knowledge nodes

The heart of knowledge extraction. Each skill contains 8-15 **Knowledge Nodes** — structured epistemic rules and operational instructions.

### Epistemic Nodes

OntoCore organizes knowledge into **10 dimensions** with **26 epistemic node types**:

#### Dimension 1: NormativeRule
Rules that define what's correct, incorrect, or constrained.

| Type | Description | Example |
|------|-------------|---------|
| **Standard** | The correct practice | "Use SPARQL for ontology queries" |
| **AntiPattern** | What to avoid | "Don't read entire files into memory for >100MB" |
| **Constraint** | Explicit limitations | "Only works on Unix" |

#### Dimension 2: StrategicInsight
Strategic insights for effective decisions.

| Type | Description | Example |
|------|-------------|---------|
| **Heuristic** | Rules of thumb | "Prefer streaming for large files" |
| **DesignPrinciple** | Architectural principles | "One skill = one responsibility" |
| **WorkflowStrategy** | Process strategies | "Compile dependencies first" |

#### Dimension 3: ResilienceTactic
How to handle problems and recover.

| Type | Description | Example |
|------|-------------|---------|
| **KnownIssue** | Known problems | "Timeout on slow networks" |
| **RecoveryTactic** | How to recover | "Retry with exponential backoff" |

#### Dimension 4: ExecutionPhysics
Physical characteristics of execution.

| Type | Description | Example |
|------|-------------|---------|
| **Idempotency** | Safe to repeat | "Compilation is idempotent" |
| **SideEffect** | Side effects | "Writes files to ontoskills/" |
| **PerformanceProfile** | Performance characteristics | "O(n) on number of skills" |

#### Dimension 5: Observability
How to observe and measure.

| Type | Description | Example |
|------|-------------|---------|
| **SuccessIndicator** | Success signals | ".ttl file generated without SHACL errors" |
| **TelemetryPattern** | Telemetry patterns | "Log extraction time per skill" |

#### Dimension 6: SecurityGuardrail
Security guardrails.

| Type | Description | Example |
|------|-------------|---------|
| **SecurityImplication** | Security implications | "Requires API key in env var" |
| **DestructivePotential** | Destructive potential | "Can overwrite existing files" |
| **FallbackStrategy** | Fallback strategies | "Use cache if offline" |

#### Dimension 7: CognitiveBoundary
Cognitive limits and ambiguity.

| Type | Description | Example |
|------|-------------|---------|
| **RequiresHumanClarification** | When to ask the user | "Ambiguous intent → ask for confirmation" |
| **AssumptionBoundary** | Assumptions made | "Assumes UTF-8 encoding" |
| **AmbiguityTolerance** | Ambiguity tolerance | "Accepts both .md and .MD" |

#### Dimension 8: ResourceProfile
Resource profile.

| Type | Description | Example |
|------|-------------|---------|
| **TokenEconomy** | Token usage | "SPARQL query: ~100 tokens vs 50KB skill files" |
| **ComputeCost** | Compute cost | "LLM extraction: ~2s per skill" |

#### Dimension 9: TrustMetric
Trust metrics.

| Type | Description | Example |
|------|-------------|---------|
| **ExecutionDeterminism** | How deterministic | "SPARQL: 100% deterministic" |
| **DataProvenance** | Data provenance | "Compiled by Claude 4 with verified hash" |

#### Dimension 10: LifecycleHook
Lifecycle hooks.

| Type | Description | Example |
|------|-------------|---------|
| **PreFlightCheck** | Pre-execution checks | "Verify ANTHROPIC_API_KEY is set" |
| **PostFlightValidation** | Post-execution validation | "Validate .ttl with SHACL" |
| **RollbackProcedure** | How to roll back | "Restore from .bak if validation fails" |

---

### Operational Nodes

In addition to epistemic knowledge, OntoCore extracts **operational nodes** — compact, actionable instructions that tell the agent what to *do*. These condense verbose skill documentation into directly executable directives.

| Type | Description | Special Fields | Example |
|------|-------------|----------------|---------|
| **Procedure** | Ordered step sequence | `step_order` (integer) | "1. Write failing test → 2. Run → 3. Minimal code → 4. Refactor" |
| **CodePattern** | Reusable code snippet | `code_language` | `def test_add(): assert add(1,2) == 3` |
| **OutputFormat** | Expected output template | `template_variables` | "## Summary\n- Finding\n- Recommendation" |
| **Command** | CLI command with exact syntax | — | `pytest tests/ -v --tb=short` |
| **Prerequisite** | Required precondition | — | "Python 3.10+ must be installed" |

Each skill generates 3-8 operational nodes. The compiler aggressively compacts multi-line instructions into minimal directives — removing filler words, explanations, and motivational text. Only what the agent *needs to do* is preserved.

#### How operational nodes help

| Without operational nodes | With operational nodes |
|---|---|
| Agent reads full SKILL.md (5-20KB) | Agent queries specific directives (~200 bytes) |
| Instructions buried in prose | Numbered procedures, exact commands |
| Code examples mixed with explanation | Minimal snippets with language context |
| Output format implicit | Explicit template with variables |
| Prerequisites scattered | Single prerequisite check list |

---

### Knowledge node structure

Each Knowledge Node has:

**Epistemic node** (reasoning about the skill):

```turtle
oc:kn_a1b2c3d4
  a oc:Heuristic ;
  oc:directiveContent "Prefer streaming for files >100MB" ;
  oc:appliesToContext "When processing large files" ;
  oc:hasRationale "Avoids OOM errors on low-RAM machines" ;
  oc:severityLevel "HIGH" .
```

**Operational node** (what to do):

```turtle
oc:kn_e5f6g7h8
  a oc:Procedure ;
  oc:directiveContent "1. Write failing test 2. Run test 3. Write minimal code 4. Refactor" ;
  oc:stepOrder 1 ;
  oc:appliesToContext "When implementing new features" .
```

| Field | Description |
|-------|-------------|
| `directiveContent` | The rule, insight, or instruction |
| `appliesToContext` | When it applies |
| `hasRationale` | Why this rule exists (epistemic only) |
| `severityLevel` | Importance: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` |
| `stepOrder` | Step position for Procedure nodes |
| `codeLanguage` | Programming language for CodePattern nodes |
| `templateVariables` | Placeholder names for OutputFormat nodes |

---

## Modular architecture

### The skill as module

Each compiled skill is a **self-contained `.ttl` file**:

```
ontoskills/
├── core.ttl      # Core TBox (shared)
├── index.ttl                # Manifest with owl:imports
├── pdf/
│   └── ontoskill.ttl        # PDF skill module
├── markdown/
│   └── ontoskill.ttl        # Markdown skill module
└── email/
    └── ontoskill.ttl        # Email skill module
```

### Pluggable knowledge

- **Add** a skill → Drop a `.ttl` file
- **Remove** a skill → Delete the `.ttl` file
- **Update** a skill → Replace the `.ttl` file

The global ontology grows by **addition**, not modification.

---

## Querying the knowledge

### Find skills by intent

```sparql
SELECT ?skill WHERE {
  ?skill oc:resolvesIntent "create_pdf"
}
```

### Get knowledge nodes for a skill

```sparql
SELECT ?content ?type WHERE {
  <skill:pdf> oc:impartsKnowledge ?node .
  ?node oc:directiveContent ?content .
  ?node a ?type .
}
```

### Find all AntiPatterns

```sparql
SELECT ?skill ?content WHERE {
  ?skill oc:impartsKnowledge ?node .
  ?node a oc:AntiPattern .
  ?node oc:directiveContent ?content .
}
```

### Find all PreFlightChecks

```sparql
SELECT ?skill ?content WHERE {
  ?skill oc:impartsKnowledge ?node .
  ?node a oc:PreFlightCheck .
  ?node oc:directiveContent ?content .
}
```

---

## The value proposition

| Before (Reading Files) | After (Ontology Query) |
|------------------------|------------------------|
| Parse 50 SKILL.md files | Single SPARQL query |
| ~500KB text scan | ~1KB query |
| Non-deterministic | Exact results |
| Context overflow | Query only what you need |
| LLM interprets | Graph returns |

**Knowledge becomes queryable. Intelligence becomes democratized.**
