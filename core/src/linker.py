"""Post-serialization link inference for intra-skill node interconnection.

Adds three types of links to the RDF graph after serialization:
1. derivedFromSection — KnowledgeNode -> Section (token overlap matching)
2. correctAlternative — AntiPattern -> Section/CodeExample (keyword matching)
3. appliesToStep — KnowledgeNode -> WorkflowStep (numeric reference matching)

The graph is modified in-place. Each strategy returns the count of links it added;
infer_links() returns the total.
"""

import logging
import re

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF

logger = logging.getLogger(__name__)

_OC_BASE = "https://ontoskills.sh/ontology#"


def _oc(local_name: str) -> URIRef:
    """Return the full URI for an OntoSkills ontology term."""
    return URIRef(f"{_OC_BASE}{local_name}")


# ---------------------------------------------------------------------------
# Strategy 1: derivedFromSection
# ---------------------------------------------------------------------------

def _infer_derived_from_section(graph: Graph) -> int:
    """Link each KnowledgeNode to the section with the highest token overlap.

    For every KnowledgeNode (reachable via oc:impartsKnowledge), this finds the
    oc:Section whose oc:sectionTitle shares the most word tokens with the KN's
    oc:appliesToContext.  A link is created only when the overlap is >= 2 tokens
    and the KN does not already have an oc:derivedFromSection triple.
    """
    count = 0

    # Build section catalogue: {section_uri: title_text}
    sections: dict[URIRef, str] = {}
    for sec in graph.subjects(RDF.type, _oc("Section")):
        titles = list(graph.objects(sec, _oc("sectionTitle")))
        if titles:
            sections[sec] = str(titles[0])

    if not sections:
        logger.debug("No sections found; skipping derivedFromSection inference")
        return 0

    # Collect every KnowledgeNode referenced by a skill
    knowledge_nodes: set[URIRef] = set()
    for _, _, kn in graph.triples((None, _oc("impartsKnowledge"), None)):
        knowledge_nodes.add(kn)

    for kn in knowledge_nodes:
        # Skip if already linked
        if any(graph.triples((kn, _oc("derivedFromSection"), None))):
            continue

        # Need appliesToContext text for matching
        contexts = list(graph.objects(kn, _oc("appliesToContext")))
        if not contexts:
            continue
        context_text = str(contexts[0]).lower()
        context_tokens = set(re.findall(r"\w+", context_text))

        if not context_tokens:
            continue

        # Find the section with highest token overlap
        best_section: URIRef | None = None
        best_score = 0
        for sec, title in sections.items():
            title_tokens = set(re.findall(r"\w+", title.lower()))
            overlap = len(context_tokens & title_tokens)
            if overlap > best_score:
                best_score = overlap
                best_section = sec

        # Require at least 2 overlapping tokens
        if best_section is not None and best_score >= 2:
            graph.add((kn, _oc("derivedFromSection"), best_section))
            count += 1
            logger.debug(
                "derivedFromSection: %s -> %s (overlap=%d)",
                kn, best_section, best_score,
            )

    logger.debug("derivedFromSection: added %d links", count)
    return count


# ---------------------------------------------------------------------------
# Strategy 2: correctAlternative
# ---------------------------------------------------------------------------

# Keywords that signal a "correct approach" section
_CORRECT_KEYWORDS = frozenset({
    "correct", "recommended", "proper", "instead",
    "best practice", "right way", "should",
})


def _infer_correct_alternative(graph: Graph) -> int:
    """Link AntiPatterns to sibling sections/code-examples with correct approach.

    For each AntiPattern with a derivedFromSection link:
    1. Find the parent of that section (via oc:hasSection / oc:hasSubsection).
    2. Search sibling sections for titles containing a correct-approach keyword.
    3. If exactly one candidate is found, link with oc:correctAlternative.
    4. If no section candidate, look for CodeExample blocks inside the same
       parent section and link if exactly one is found.
    """
    count = 0

    anti_patterns: set[URIRef] = set()
    for ap in graph.subjects(RDF.type, _oc("AntiPattern")):
        anti_patterns.add(ap)

    if not anti_patterns:
        return 0

    for ap in anti_patterns:
        # Skip if already linked
        if any(graph.triples((ap, _oc("correctAlternative"), None))):
            continue

        # Must have a derivedFromSection (from Strategy 1)
        derived_secs = list(graph.objects(ap, _oc("derivedFromSection")))
        if not derived_secs:
            continue
        ap_section = derived_secs[0]

        # Find the parent of ap_section
        parents = list(graph.subjects(_oc("hasSection"), ap_section))
        parents += list(graph.subjects(_oc("hasSubsection"), ap_section))
        if not parents:
            continue
        parent = parents[0]

        # Collect sibling sections (children of the same parent, excluding self)
        siblings: list[URIRef] = []
        for sib in graph.objects(parent, _oc("hasSection")):
            if sib != ap_section:
                siblings.append(sib)
        for sib in graph.objects(parent, _oc("hasSubsection")):
            if sib != ap_section:
                siblings.append(sib)

        # Search siblings for keyword-matched titles
        candidates: list[URIRef] = []
        for sib in siblings:
            titles = list(graph.objects(sib, _oc("sectionTitle")))
            if not titles:
                continue
            title_lower = str(titles[0]).lower()
            if any(kw in title_lower for kw in _CORRECT_KEYWORDS):
                candidates.append(sib)

        # Conservative: link only when exactly one candidate
        if len(candidates) == 1:
            graph.add((ap, _oc("correctAlternative"), candidates[0]))
            count += 1
            logger.debug(
                "correctAlternative: %s -> %s (keyword match)",
                ap, candidates[0],
            )
            continue

        # Fallback: look for CodeExample blocks inside ap_section itself
        if not any(graph.triples((ap, _oc("correctAlternative"), None))):
            code_candidates: list[URIRef] = []
            for content in graph.objects(ap_section, _oc("hasContent")):
                if any(graph.triples((content, RDF.type, _oc("CodeExample")))):
                    code_candidates.append(content)
            if len(code_candidates) == 1:
                graph.add((ap, _oc("correctAlternative"), code_candidates[0]))
                count += 1
                logger.debug(
                    "correctAlternative: %s -> %s (code example fallback)",
                    ap, code_candidates[0],
                )

    logger.debug("correctAlternative: added %d links", count)
    return count


# ---------------------------------------------------------------------------
# Strategy 3: appliesToStep
# ---------------------------------------------------------------------------

# Patterns like "step N", "#N", "Nth step"
_STEP_NUM_RE = re.compile(
    r"(?:step\s+(?P<n>\d+)|#(?P<hash_n>\d+)|(?P<ordinal>\d+)(?:st|nd|rd|th)\s+step)",
    re.IGNORECASE,
)


def _infer_applies_to_step(graph: Graph) -> int:
    """Link KnowledgeNodes to WorkflowSteps by numeric references.

    For each KnowledgeNode, examine oc:appliesToContext for step-number
    references (e.g. "step 3", "#2", "1st step").  If exactly one
    WorkflowStep has a matching oc:stepOrder, link with oc:appliesToStep.

    Also attempts substring matching against oc:stepLabel when present.
    """
    count = 0

    # Build step catalogue: {step_uri: {id, order, label}}
    steps: dict[URIRef, dict] = {}
    for step in graph.subjects(RDF.type, _oc("WorkflowStep")):
        ids = list(graph.objects(step, _oc("stepId")))
        orders = list(graph.objects(step, _oc("stepOrder")))
        labels = list(graph.objects(step, _oc("stepLabel")))
        steps[step] = {
            "id": str(ids[0]) if ids else "",
            "order": int(orders[0]) if orders else -1,
            "label": str(labels[0]) if labels else "",
        }

    if not steps:
        logger.debug("No workflow steps found; skipping appliesToStep inference")
        return 0

    # Collect every KnowledgeNode
    knowledge_nodes: set[URIRef] = set()
    for _, _, kn in graph.triples((None, _oc("impartsKnowledge"), None)):
        knowledge_nodes.add(kn)

    for kn in knowledge_nodes:
        # Skip if already linked
        if any(graph.triples((kn, _oc("appliesToStep"), None))):
            continue

        contexts = list(graph.objects(kn, _oc("appliesToContext")))
        if not contexts:
            continue
        context_text = str(contexts[0])

        # --- Numeric reference matching ---
        for match in _STEP_NUM_RE.finditer(context_text):
            step_num = (
                match.group("n")
                or match.group("hash_n")
                or match.group("ordinal")
            )
            if step_num is None:
                continue
            step_num_int = int(step_num)
            matching = [
                s for s, info in steps.items()
                if info["order"] == step_num_int
            ]
            if len(matching) == 1:
                graph.add((kn, _oc("appliesToStep"), matching[0]))
                count += 1
                logger.debug(
                    "appliesToStep: %s -> %s (step order=%d)",
                    kn, matching[0], step_num_int,
                )
                break  # one link per KN is enough
            # If multiple or zero matches, continue trying other patterns

        # If already linked by numeric match, move on
        if any(graph.triples((kn, _oc("appliesToStep"), None))):
            continue

        # --- Label substring matching ---
        context_lower = context_text.lower()
        matching = [
            s for s, info in steps.items()
            if info["label"] and info["label"].lower() in context_lower
        ]
        if len(matching) == 1:
            graph.add((kn, _oc("appliesToStep"), matching[0]))
            count += 1
            logger.debug(
                "appliesToStep: %s -> %s (label match '%s')",
                kn, matching[0], steps[matching[0]]["label"],
            )

    logger.debug("appliesToStep: added %d links", count)
    return count


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def infer_links(graph: Graph) -> int:
    """Run all link inference strategies on the graph.

    The graph is modified in-place.  Returns the total number of link triples
    added across all three strategies.

    Strategies run in dependency order:
    1. derivedFromSection  (needed by strategy 2)
    2. correctAlternative  (uses derivedFromSection from strategy 1)
    3. appliesToStep       (independent)
    """
    total = 0
    total += _infer_derived_from_section(graph)
    total += _infer_correct_alternative(graph)
    total += _infer_applies_to_step(graph)
    logger.info("Link inference complete: %d links added", total)
    return total
