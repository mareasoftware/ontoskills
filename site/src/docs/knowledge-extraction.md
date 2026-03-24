---
title: Knowledge Extraction
description: How OntoCore extracts structured knowledge from skills
---

A skill is not just code — it's **structured knowledge**. OntoCore extracts this knowledge and compiles it into a queryable ontology.

---

## What Gets Extracted

Every skill is compiled with:

| Element | Property | Description |
|----------|-----------|-------------|
| **Identity** | `oc:nature`, `oc:genus`, `oc:differentia` | "A is a B that C" definition |
| **Intents** | `oc:resolvesIntent` | What user intentions this skill resolves |
| **Requirements** | `oc:hasRequirement` | Dependencies (EnvVar, Tool, Hardware, API, Knowledge) |
| **Knowledge Nodes** | `oc:impartsKnowledge` | Epistemic knowledge (8-12 per skill) |
| **State Transitions** | `oc:requiresState`, `oc:yieldsState`, `oc:handlesFailure` | Preconditions, outcomes, error handling |
| **Execution Payload** | `oc:hasPayload` | Optional code to execute |
| **Provenance** | `oc:generatedBy` | Attestation (which LLM compiled it) |

---

## Knowledge Nodes

The heart of knowledge extraction. Each skill contains 8-12 **Knowledge Nodes** — structured epistemic rules.

### The 10 Epistemic Dimensions

OntoCore organizes knowledge into **10 dimensions** with **26 node types**:

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

### Knowledge Node Structure

Each Knowledge Node has:

```turtle
oc:kn_a1b2c3d4
  a oc:Heuristic ;
  oc:directiveContent "Prefer streaming for files >100MB" ;
  oc:appliesToContext "When processing large files" ;
  oc:hasRationale "Avoids OOM errors on low-RAM machines" ;
  oc:severityLevel "HIGH" .
```

| Field | Description |
|-------|-------------|
| `directiveContent` | The rule or insight |
| `appliesToContext` | When it applies |
| `hasRationale` | Why this rule exists |
| `severityLevel` | Importance: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` |

---

## Modular Architecture

### The Skill as Module

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

### Find All AntiPatterns

```sparql
SELECT ?skill ?content WHERE {
  ?skill oc:impartsKnowledge ?node .
  ?node a oc:AntiPattern .
  ?node oc:directiveContent ?content .
}
```

### Find All PreFlightChecks

```sparql
SELECT ?skill ?content WHERE {
  ?skill oc:impartsKnowledge ?node .
  ?node a oc:PreFlightCheck .
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
| Context overflow | Query only what you need |
| LLM interprets | Graph returns |

**Knowledge becomes queryable. Intelligence becomes democratized.**
