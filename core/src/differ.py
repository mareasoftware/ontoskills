"""
Semantic diff engine for OntoSkills Skill Drift Detector.

Compares two RDF graphs at the triple level and classifies differences
by semantic category: intents, states, requirements, and relations.
"""

from dataclasses import dataclass, field
from typing import Literal

from rdflib import Graph, Namespace, URIRef

OC = Namespace('https://ontoskills.sh/ontology#')
OC_PREFIX = str(OC)  # For SPARQL queries

ChangeType = Literal['breaking', 'additive', 'cosmetic']


@dataclass
class MigrationSuggestion:
    """Actionable migration guidance generated for a single breaking change."""
    skill_id: str
    category: str
    summary: str            # one-line human description
    sparql_query: str       # SPARQL to locate affected agents/callers
    action: str             # what the developer should do


@dataclass
class SkillChange:
    skill_id: str
    change_type: ChangeType
    category: str  # 'intent', 'state', 'requirement', 'relation', 'metadata'
    description: str
    old_value: str | None = None
    new_value: str | None = None


@dataclass
class DriftReport:
    breaking: list[SkillChange] = field(default_factory=list)
    additive: list[SkillChange] = field(default_factory=list)
    cosmetic: list[SkillChange] = field(default_factory=list)
    removed_skills: list[str] = field(default_factory=list)
    added_skills: list[str] = field(default_factory=list)

    @property
    def has_breaking(self) -> bool:
        return bool(self.breaking or self.removed_skills)

    @property
    def is_clean(self) -> bool:
        return not (
            self.breaking
            or self.additive
            or self.cosmetic
            or self.removed_skills
            or self.added_skills
        )

    def suggestions(self) -> list[MigrationSuggestion]:
        """Generate actionable migration suggestions for every breaking change."""
        result: list[MigrationSuggestion] = []

        for sid in self.removed_skills:
            local = sid.split('#')[-1].split('/')[-1]
            result.append(MigrationSuggestion(
                skill_id=local,
                category='skill-removed',
                summary=f"Skill '{local}' was removed from the ontology",
                sparql_query=(
                    f'PREFIX oc: <{OC_PREFIX}>\n'
                    f'SELECT ?agent WHERE {{\n'
                    f'  ?agent oc:dependsOn oc:{local} .\n'
                    f'}}'
                ),
                action=(
                    f"Remove or replace all oc:dependsOn oc:{local} references. "
                    f"Check if a replacement skill covers the same intents."
                ),
            ))

        for change in self.breaking:
            if change.category == 'intent' and change.old_value:
                result.append(MigrationSuggestion(
                    skill_id=change.skill_id,
                    category='intent-renamed',
                    summary=(
                        f"Intent '{change.old_value}' removed from '{change.skill_id}'"
                        + (f" (replaced by '{change.new_value}')" if change.new_value else "")
                    ),
                    sparql_query=(
                        f'PREFIX oc: <{OC_PREFIX}>\n'
                        f'SELECT ?skill WHERE {{\n'
                        f'  ?skill oc:resolvesIntent "{change.old_value}" .\n'
                        f'}}'
                    ),
                    action=(
                        f"Update all agents and queries that reference intent "
                        f"'{change.old_value}'"
                        + (f" to use '{change.new_value}' instead." if change.new_value
                           else ". No replacement intent was found in the new ontology.")
                    ),
                ))

            elif change.category == 'state' and change.old_value:
                result.append(MigrationSuggestion(
                    skill_id=change.skill_id,
                    category='state-removed',
                    summary=f"State '{change.old_value}' removed from '{change.skill_id}'",
                    sparql_query=(
                        f'PREFIX oc: <{OC_PREFIX}>\n'
                        f'SELECT ?skill WHERE {{\n'
                        f'  ?skill oc:requiresState oc:{change.old_value.split("#")[-1]} .\n'
                        f'}}'
                    ),
                    action=(
                        f"Review state machine transitions. '{change.old_value}' is no longer "
                        f"declared as a precondition for '{change.skill_id}'. "
                        f"Update agent planning logic accordingly."
                    ),
                ))

            elif change.category == 'requirement' and change.new_value:
                req_local = change.new_value.split('#')[-1].split('/')[-1]
                result.append(MigrationSuggestion(
                    skill_id=change.skill_id,
                    category='requirement-added',
                    summary=f"New requirement '{req_local}' added to '{change.skill_id}'",
                    sparql_query=(
                        f'PREFIX oc: <{OC_PREFIX}>\n'
                        f'SELECT ?skill WHERE {{\n'
                        f'  ?skill oc:hasRequirement oc:{req_local} .\n'
                        f'}}'
                    ),
                    action=(
                        f"Ensure all agents invoking '{change.skill_id}' can satisfy "
                        f"the new requirement '{req_local}' before execution."
                    ),
                ))

        return result


def compute_diff(old_ttl: str, new_ttl: str) -> DriftReport:
    """Compare two .ttl files and return a DriftReport."""
    g_old, g_new = Graph(), Graph()
    g_old.parse(old_ttl, format='turtle')
    g_new.parse(new_ttl, format='turtle')

    report = DriftReport()
    report.removed_skills = _find_removed_skills(g_old, g_new)
    report.added_skills = _find_added_skills(g_old, g_new)

    for skill_uri in _all_skills(g_old):
        if str(skill_uri) in report.removed_skills:
            continue
        sid = _local_name(skill_uri)
        _diff_intents(g_old, g_new, skill_uri, sid, report)
        _diff_states(g_old, g_new, skill_uri, sid, report)
        _diff_requirements(g_old, g_new, skill_uri, sid, report)
        _diff_knowledge_nodes(g_old, g_new, skill_uri, sid, report)

    return report


# ─── Private helpers ──────────────────────────────────────────────────


def _all_skills(g: Graph) -> list[URIRef]:
    return list(g.subjects(predicate=OC.resolvesIntent))


def _find_removed_skills(g_old: Graph, g_new: Graph) -> list[str]:
    old_ids = {str(s) for s in _all_skills(g_old)}
    new_ids = {str(s) for s in _all_skills(g_new)}
    return list(old_ids - new_ids)


def _find_added_skills(g_old: Graph, g_new: Graph) -> list[str]:
    old_ids = {str(s) for s in _all_skills(g_old)}
    new_ids = {str(s) for s in _all_skills(g_new)}
    return list(new_ids - old_ids)


def _local_name(uri: URIRef) -> str:
    return str(uri).split('#')[-1].split('/')[-1]


def _diff_intents(
    g_old: Graph, g_new: Graph, skill_uri: URIRef, sid: str, report: DriftReport
) -> None:
    old_intents = {str(o) for o in g_old.objects(skill_uri, OC.resolvesIntent)}
    new_intents = {str(o) for o in g_new.objects(skill_uri, OC.resolvesIntent)}

    for removed in old_intents - new_intents:
        report.breaking.append(
            SkillChange(
                skill_id=sid,
                change_type='breaking',
                category='intent',
                description=f'Removed intent: {removed}',
                old_value=removed,
                new_value=None,
            )
        )
    for added in new_intents - old_intents:
        report.additive.append(
            SkillChange(
                skill_id=sid,
                change_type='additive',
                category='intent',
                description=f'Added intent: {added}',
                old_value=None,
                new_value=added,
            )
        )


def _diff_states(
    g_old: Graph, g_new: Graph, skill_uri: URIRef, sid: str, report: DriftReport
) -> None:
    for prop in [OC.requiresState, OC.yieldsState]:
        old_v = {str(o) for o in g_old.objects(skill_uri, prop)}
        new_v = {str(o) for o in g_new.objects(skill_uri, prop)}
        pname = str(prop).split('#')[-1]

        for removed in old_v - new_v:
            report.breaking.append(
                SkillChange(
                    skill_id=sid,
                    change_type='breaking',
                    category='state',
                    description=f'{pname} removed: {removed}',
                    old_value=removed,
                )
            )
        for added in new_v - old_v:
            report.additive.append(
                SkillChange(
                    skill_id=sid,
                    change_type='additive',
                    category='state',
                    description=f'{pname} added: {added}',
                    new_value=added,
                )
            )


def _diff_requirements(
    g_old: Graph, g_new: Graph, skill_uri: URIRef, sid: str, report: DriftReport
) -> None:
    """Diff oc:hasRequirement - added requirements are breaking (agents may lack them)."""
    old_reqs = {str(o) for o in g_old.objects(skill_uri, OC.hasRequirement)}
    new_reqs = {str(o) for o in g_new.objects(skill_uri, OC.hasRequirement)}

    for removed in old_reqs - new_reqs:
        report.additive.append(
            SkillChange(
                skill_id=sid,
                change_type='additive',
                category='requirement',
                description=f'Requirement removed: {removed}',
                old_value=removed,
            )
        )
    for added in new_reqs - old_reqs:
        report.breaking.append(
            SkillChange(
                skill_id=sid,
                change_type='breaking',
                category='requirement',
                description=f'New requirement added: agents may not have {added}',
                new_value=added,
            )
        )


def _diff_knowledge_nodes(
    g_old: Graph, g_new: Graph, skill_uri: URIRef, sid: str, report: DriftReport
) -> None:
    """Diff oc:impartsKnowledge - knowledge changes are informational (cosmetic)."""
    old_kn = {str(o) for o in g_old.objects(skill_uri, OC.impartsKnowledge)}
    new_kn = {str(o) for o in g_new.objects(skill_uri, OC.impartsKnowledge)}

    for removed in old_kn - new_kn:
        report.cosmetic.append(
            SkillChange(
                skill_id=sid,
                change_type='cosmetic',
                category='knowledge',
                description=f'Knowledge node removed: {_local_name_from_uri(removed)}',
                old_value=removed,
            )
        )
    for added in new_kn - old_kn:
        report.cosmetic.append(
            SkillChange(
                skill_id=sid,
                change_type='cosmetic',
                category='knowledge',
                description=f'Knowledge node added: {_local_name_from_uri(added)}',
                new_value=added,
            )
        )


def _local_name_from_uri(uri_str: str) -> str:
    """Extract local name from a full URI string."""
    return uri_str.split('#')[-1].split('/')[-1]
