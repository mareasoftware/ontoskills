# OntoSkills × Our Systems — Integration Blueprint

## Current Reality

All our agents (wisp, research-lab, devops-agent) follow the same pattern:

```
Agent gets task → reads SKILL.md files → LLM interprets → acts
                                        ↑
                                   PROBABILISTIC
                              (same query, different results)
```

## Target Architecture

```
Agent gets task → SPARQL query ontology → exact skill → acts
                            ↑
                       DETERMINISTIC
                    (same query, same result, every time)
```

---

## System 1: Wisp (CLI Coding Agent)

**Current:** Skills loaded from `.warp/skills/`, `.claude/skills/`, `.agents/skills/`

**Integration path:**

### Step 1: Compile wisp skills to ontology

```bash
cd ~/Documents/wisp
ontocore compile --skills-dir skills/ --output ~/.ontoskills/wisp/
```

### Step 2: Replace skill loader in wisp

```python
# In wisp/wisp/skills.py — add ontology-backed loader

from wisp_skill_bridge import OntologySkillProvider

class HybridSkillLoader:
    """Tries ontology first, falls back to raw file reading."""
    
    def __init__(self):
        self.ontology = OntologySkillProvider(
            skills_dir="./skills",
            ontology_dir=os.path.expanduser("~/.ontoskills/wisp"),
        )
        self.registry = get_registry()  # Original markdown loader
    
    async def load_for_task(self, prompt: str) -> str:
        # Try ontology first
        try:
            context = await self.ontology.resolve(prompt)
            if context and "No ontology skills matched" not in context:
                return f"[ONTOLOGY] {context}"
        except Exception:
            pass
        
        # Fall back to raw file reading
        return self.registry.build_system_prompt(prompt)
```

**Impact:**
- Skill selection: probabilistic → deterministic
- Token usage: ~500KB skill text → ~1KB query
- Works on small models (qwen3:4b, phi-3-mini)
- Wisp can now run efficiently on Android/Termux with 4B models

---

## System 2: Research Lab Agents (13-Agent Swarm)

**Current:** 13 agents each loading prompt templates from `prompts/*.txt`. Planner hardcodes task graph.

**Integration path:**

### Step 1: Compile agent prompts + research skills to ontology

```bash
cd ~/Documents/research-lab-agents

# Compile agent prompts as skills
ontocore compile \
  --skills-dir prompts/ \
  --output ~/.ontoskills/research-lab/

# Also compile research methodology skills
ontocore compile \
  --skills-dir skills/ \
  --output ~/.ontoskills/research-methods/
```

### Step 2: Ontology-backed Planner

```python
# In src/agents/meta/planner.py

class OntologyPlanner(Planner):
    """Planner that queries ontology instead of hardcoding task graph."""
    
    async def run(self, state, **kwargs):
        # Query ontology for execution plan
        plan = await self.ontology.evaluate_plan(
            intent=state.goal,
            current_states=[state.current_phase.value],
        )
        
        if plan.skill_chain:
            # Convert ontology plan to tasks
            state.task_graph = [
                Task(task_id=f"t{i}", description=sid, agent=sid_to_agent(sid))
                for i, sid in enumerate(plan.skill_chain, 1)
            ]
        
        return AgentOutput(content=f"Plan: {plan}", tasks=state.task_graph)
```

### Step 3: Ontology-backed Supervisor

```python
# Instead of hardcoded routing rules:
# "if task agent == literature_reviewer → route to lit_reviewer node"
# Use SPARQL:
# "SELECT ?skill WHERE { ?skill oc:resolvesIntent ?intent }"
```

**Impact:**
- Planner: 9 hardcoded tasks → dynamic ontology-derived plan
- Supervisor: if/elif chain → SPARQL query
- Each agent gets deterministic context for its specific sub-task
- 13 agents × 50KB prompts → 13 × 1KB queries

---

## System 3: DevOps Agent (Infrastructure Automation)

**Current:** 5 skills (terraform-aws, kubernetes-manifests, github-actions, security-scan, cost-optimization). Skills matched via keyword scoring.

**Integration path:**

### Step 1: Compile DevOps skills

```bash
cd ~/Documents/devops-agent
ontocore compile --skills-dir skills/ --output ~/.ontoskills/devops/
```

### Step 2: Replace keyword matcher with ontology queries

```python
# In control-plane/skills.py

class OntologySkillRegistry(SkillRegistry):
    """Keyword matching → SPARQL queries."""
    
    def match_for_task(self, prompt: str) -> List[Skill]:
        # Query ontology instead of keyword counting
        client = get_ontology_client()
        results = await client.search(prompt, top_k=5)
        
        return [
            Skill(name=r.skill_id, description=r.description)
            for r in results
        ]
```

### Step 3: Execution plan for complex tasks

```python
# For: "Create production EKS cluster with monitoring and CI/CD"
plan = await client.evaluate_plan(
    intent="deploy_eks_cluster",
    current_states=["infrastructure_defined"],
)
# → [terraform-aws, kubernetes-manifests, github-actions, prometheus-rules]
```

**Impact:**
- "Create VPC" → exact match to terraform-aws, not keyword guess
- Multi-step tasks get deterministic execution chains
- Security scan results become queryable epistemic rules
- Drift detection: compare ontology vs actual infra state

---

## System 4: Pi / Hermes (Agent Framework)

**Current:** Skills loaded as markdown files in `.agents/skills/`

**Integration:**

```python
# Pi extension that loads skills from ontology
# In ~/.pi/agent/extensions/ontoskills.py

from ontoskills import OntoSkillsClient
from ontoskills.formatter import ContextFormatter

class OntoSkillsExtension:
    """Pi extension: query ontologies instead of reading skill files."""
    
    async def on_query(self, prompt: str):
        client = OntoSkillsClient(
            ontology_root=os.path.expanduser("~/.ontoskills/pi-skills/"),
        )
        async with client:
            results = await client.prefetch_knowledge(
                query=prompt, max_skills=3,
            )
            return ContextFormatter.format_multi_context(results, prompt)
```

---

## Unified Deployment: Single Ontology Server

Instead of each system running its own ontomcp, run **one shared server**:

```bash
# Compile ALL skills into one ontology
cd ~/Documents
ontocore compile \
  --skills-dir wisp/skills/ \
  --skills-dir research-lab-agents/prompts/ \
  --skills-dir devops-agent/skills/ \
  --output ~/.ontoskills/unified/

# Start one shared OntoMCP server
ontomcp --ontology-root ~/.ontoskills/unified/ &

# All agents connect to it
export ONTOSKILLS_SERVER=stdio://ontomcp
```

Now every agent in your ecosystem gets:
- Deterministic skill resolution
- Cross-project skill discovery (devops skill visible to research agent)
- Shared epistemic rules (security policies across all agents)
- Single point of skill compilation/validation

---

## Migration Roadmap

| Phase | What | When |
|-------|------|------|
| **1** | Compile DevOps skills, test with keyword→SPARQL | This week |
| **2** | Compile Research agents, test Planner ontology | Next week |
| **3** | Wire Wisp skill bridge, test on Android/Termux | Week 3 |
| **4** | Unified ontology server, cross-project queries | Week 4 |

**Prerequisites for each phase:**
- `ontocore` installed (Python)
- `ontomcp` built (Rust, `cargo build --release` in mcp/)
- `ontoskills-py` installed (our PR, `pip install contrib/ontoskills-py/`)
