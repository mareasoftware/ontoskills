---
name: ontomcp-driver
description: Protocol for interacting with the OntoSkills MCP server to discover, evaluate, and compose skills from the compiled knowledge graph.
---

## OVERVIEW

The OntoSkills MCP server exposes a knowledge graph of compiled skills. This document teaches you how to use its 5 tools effectively to find, evaluate, and compose skills for any task.

## AVAILABLE MCP TOOLS

### 1. search({ query: string }) -> Vec<SkillSearchResult>

Search across all compiled skills by keyword (BM25), alias, or structured filters. Returns matching skills with relevance indicators.

**When to use:** When you need to find skills that address a user's intent or task requirement.

**Best practices:**
- Use natural language queries that describe the GOAL, not the tool name
- Example: "create a presentation from data" is better than "pptx"
- If results are sparse, try synonyms or broader terms
- Call this FIRST before any other MCP tool

### 2. get_skill_context({ skill_id: string, include_inherited_knowledge: bool = true }) -> SkillContextResult

Returns full details for a specific skill: metadata, knowledge nodes, state transitions, dependencies, and section titles (table of contents).

**When to use:** After search identified candidate skills, to evaluate fitness and see what sections are available.

**Best practices:**
- The `sections` field lists all section titles — use these with get_skill_content to read specific sections
- Set `include_inherited_knowledge=false` to exclude knowledge from extended skills
- Always check requiresState before attempting execution
- Read ALL knowledge nodes with severity CRITICAL or HIGH before proceeding

**Response structure:**
- `skill`: skill metadata (name, description, category, intents, aliases)
- `payload`: executor type and code (for executable skills)
- `knowledge_nodes`: epistemic rules (standards, anti-patterns, constraints, heuristics, etc.)
- `sections`: table of contents — list of section titles with levels and hierarchy
- `include_inherited_knowledge`: whether inherited knowledge from extended skills was included

### 3. get_skill_content({ skill_id: string, section: string = None }) -> SkillContentResult

Retrieves skill section content as reconstructed markdown. If `section` is omitted, returns the table of contents. If `section` is provided, returns the content of that section and all its subsections.

**When to use:** After get_skill_context showed available sections, to read the actual instructions, code examples, checklists, and procedures.

**Best practices:**
- Call get_skill_context first to see which sections exist
- Request sections one at a time — only load what you need
- The response includes subsections automatically — no need to request them separately
- Reconstructed markdown matches the original SKILL.md structure

**Response (no section):** TOC as markdown headings
**Response (with section):** Reconstructed markdown with paragraphs, code blocks, bullet lists, ordered procedures, tables, blockquotes, flowcharts, templates

### 4. evaluate_execution_plan({ plan: ExecutionPlan }) -> ExecutionPlanEvaluation

Validates a proposed execution plan against the skill knowledge graph. Checks state chains, dependencies, and identifies missing prerequisites.

**When to use:** Before executing a multi-skill workflow, to verify the plan is sound.

**Best practices:**
- Include ALL skills in the plan, even "obvious" ones
- Check the `applicable` field — if false, review `missing_states` and `warnings`
- Pay attention to `recommended_skill` — the graph may suggest a better alternative
- Review `plan_steps` for the correct execution order

**Plan structure:**
```json
{
  "steps": [
    {"skill_id": "skill-name", "description": "what this step accomplishes"},
    ...
  ]
}
```

### 5. query_epistemic_rules({ context: string, kind: string = None, severity: string = None }) -> Vec<KnowledgeNodeInfo>

Queries knowledge rules across all skills, optionally filtered by type and severity.

**When to use:** When you need best practices, constraints, or warnings for a specific domain/context.

**Best practices:**
- Use specific context strings: "when modifying Excel files" is better than "excel"
- Filter by severity="CRITICAL" first to catch hard constraints
- Filter by kind to get specific rule types: "AntiPattern", "Constraint", "SecurityImplication"
- This tool searches ACROSS skills — it finds rules from any skill that matches the context

## WORKFLOW

### Discovery Phase
1. Call `search` with the user's intent
2. For each match (up to 5), call `get_skill_context({ skill_id })` to see sections and requirements
3. Evaluate: check intents alignment, requiresState preconditions, category relevance
4. Select the best 1-3 candidates

### Planning Phase
5. Build an execution plan with selected skills
6. Call `evaluate_execution_plan` to validate
7. If `executable=false`: address missing_states, resolve warnings, re-evaluate
8. For CRITICAL/HIGH knowledge nodes: internalize the rules before proceeding

### Execution Phase
9. Call `get_skill_content({ skill_id, section })` for the sections you'll execute
10. Follow ordered procedures (stepOrder) if present
11. Respect all knowledge nodes — especially AntiPatterns and Constraints
12. After execution, verify yieldsState matches expected outcomes

## COMMON MISTAKES TO AVOID

- **Skipping search:** Don't guess skill names. Always search first.
- **Ignoring requiresState:** Executing a skill without its preconditions leads to failures.
- **Overlooking CRITICAL knowledge nodes:** These are hard constraints, not suggestions.
- **Not validating plans:** Multi-skill workflows can have broken state chains.
- **Loading full content too early:** Use get_skill_context first, then get_skill_content only for sections you need.
- **Assuming skill availability:** Search results only include compiled and enabled skills.

## STATE TRANSITION SEMANTICS

Skills form a state machine via requiresState/yieldsState:
- `requiresState`: What MUST be true before execution (preconditions)
- `yieldsState`: What BECOMES true after successful execution (outcomes)
- `handlesFailure`: What states indicate execution failure

State chaining: Skill A's yieldsState should match Skill B's requiresState for valid sequencing.
If evaluate_execution_plan reports `missing_states`, you need to find or ensure skills that yield those states.

## CONTENT BLOCK TYPES

When using get_skill_content, responses may contain:
- **CodeExample**: Inline code with language, purpose, and usage context
- **Table**: Markdown tables with raw source (can be reconstructed)
- **Flowchart**: Graphviz or Mermaid diagrams encoding decision flows
- **Template**: Reusable prompt/output templates with variable placeholders
- **Workflow**: Ordered procedure steps with dependencies

Use these to execute the skill without reading the original SKILL.md.
