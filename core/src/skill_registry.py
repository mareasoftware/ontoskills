"""Skill Registry - compact index of known skills for LLM context and validation.

Built from Phase 1 directory scans (same vendor/package only).
Used to:
- Inject known-skills context into the LLM system prompt
- Validate/filter extracted depends_on, extends, contradicts references
- Cross-package references are silently removed (not supported yet)
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class SkillRegistry:
    """Compact registry of skills in the same vendor/package."""

    # skill_id -> short description (from frontmatter)
    skills: dict[str, str] = field(default_factory=dict)

    # Package name for context heading
    package_name: str = ""

    @classmethod
    def build(
        cls,
        dir_scan_cache: dict[Path, object],
        package_name: str = "",
    ) -> "SkillRegistry":
        """Build registry from Phase 1 directory scans.

        Args:
            dir_scan_cache: skill_dir -> DirectoryScan (from Phase 1)
            package_name: Name of the current package (for heading)
        """
        skills: dict[str, str] = {}
        for scan in dir_scan_cache.values():
            skill_id = scan.skill_id
            description = ""
            if hasattr(scan, "frontmatter") and scan.frontmatter:
                description = getattr(scan.frontmatter, "description", "") or ""
            skills[skill_id] = description[:120]

        return cls(
            skills=skills,
            package_name=package_name,
        )

    @property
    def all_known_ids(self) -> set[str]:
        return set(self.skills.keys())

    def is_known_skill(self, skill_ref: str) -> bool:
        """Check if a skill reference matches a known skill.

        Handles bare IDs and qualified IDs (extracts last segment).
        """
        if not skill_ref:
            return False
        if skill_ref in self.skills:
            return True
        if "/" in skill_ref:
            bare = skill_ref.rsplit("/", 1)[-1]
            return bare in self.skills
        return False

    def filter_relations(
        self,
        relations: list[str],
        field_name: str,
    ) -> list[str]:
        """Filter relation list, keeping only references to known skills."""
        if not relations:
            return relations

        filtered = []
        for ref in relations:
            if self.is_known_skill(ref):
                filtered.append(ref)
            else:
                logger.warning(
                    "Filtered unknown %s reference: '%s' "
                    "(not in %d known skills for %s)",
                    field_name, ref, len(self.skills), self.package_name,
                )
        return filtered

    def build_llm_context_section(self) -> str:
        """Build the KNOWN SKILLS REGISTRY section for the LLM system prompt."""
        if not self.skills:
            return ""

        lines = ["\n## KNOWN SKILLS IN THIS PACKAGE\n"]

        pkg_label = f" ({self.package_name})" if self.package_name else ""
        lines.append(f"The following skills exist in this vendor{pkg_label}:\n")

        for skill_id, desc in sorted(self.skills.items()):
            if desc:
                lines.append(f"- `{skill_id}`: {desc}")
            else:
                lines.append(f"- `{skill_id}`")

        lines.append("")
        lines.append(
            "CRITICAL: When extracting `depends_on`, `extends`, or `contradicts`, "
            "ONLY use skill IDs from the list above. "
            "Cross-package references are NOT supported — omit them entirely. "
            "Never invent, fabricate, or guess skill IDs."
        )
        lines.append("")

        return "\n".join(lines)
