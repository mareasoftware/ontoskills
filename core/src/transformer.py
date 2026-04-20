"""
LLM Tool-Use Extraction Module.

Orchestrates the tool-use conversation with Claude to extract
structured skill data from markdown files.
"""

import json
import os
import logging
from pathlib import Path

import anthropic
from anthropic import Anthropic

from compiler.env import load_local_env
from compiler.schemas import ContentExtraction, ExtractedSkill
from compiler.exceptions import ExtractionError
from compiler.config import ANTHROPIC_MODEL, MAX_ITERATIONS, EXTRACTION_TIMEOUT
from compiler.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

load_local_env()

# Configuration
COMPLETION_TOOL = "extract_skill"


def build_sub_skill_context_prompt(
    filename: str,
    parent_skill_id: str,
    sibling_names: list[str] | None = None
) -> str:
    """
    Build the context augmentation prompt for sub-skill extraction.

    Args:
        filename: The markdown filename being extracted (e.g., "planning.md")
        parent_skill_id: The Qualified ID of the parent skill
        sibling_names: List of sibling sub-skill filenames for dependsOn inference

    Returns:
        Context string to append to system prompt
    """
    sibling_list = ""
    if sibling_names:
        # Convert filenames to skill IDs for reference
        sibling_ids = [Path(s).stem for s in sibling_names]
        sibling_list = f"\n\nSibling sub-skills in this directory: {', '.join(sibling_ids)}\nUse these IDs when deriving dependsOn relationships."

    return f"""
## SUB-SKILL CONTEXT

You are extracting a sub-skill from file "{filename}"
that is part of the parent skill "{parent_skill_id}".

Consider this context when:
- Deriving dependsOn relationships with sibling sub-skills (use their simple IDs like "setup", "planning")
- Determining appropriate intents (they may be more specific than the parent)
- Understanding the scope of the sub-skill (it operates within the parent's epistemic perimeter)
{sibling_list}

DO NOT add an "extends" relationship - this will be injected automatically by the compiler.
"""

# Tool definitions
TOOLS = [
    {
        "name": "list_files",
        "description": "List all files in the skill directory recursively.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "read_file",
        "description": "Read a file from the skill directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path from skill directory root"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "extract_skill",
        "description": "Submit the extracted skill data in structured format.",
        "input_schema": ExtractedSkill.model_json_schema()
    }
]

# Initialize Anthropic client
client = Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    base_url=os.getenv("ANTHROPIC_BASE_URL")
)


def tool_result(tool_id: str, content: str) -> dict:
    """Create a tool result message for the conversation."""
    return {
        "role": "user",
        "content": [{
            "type": "tool_result",
            "tool_use_id": tool_id,
            "content": content
        }]
    }


def execute_tool(name: str, input_data: dict, skill_dir: Path) -> str:
    """
    Execute a tool call and return JSON result.

    Args:
        name: Tool name (list_files, read_file, extract_skill)
        input_data: Tool input parameters
        skill_dir: Path to skill directory

    Returns:
        JSON string with tool result or error
    """
    try:
        if name == "list_files":
            files = [
                str(f.relative_to(skill_dir))
                for f in skill_dir.rglob("*")
                if f.is_file() and not f.name.startswith(".")
            ]
            return json.dumps({"files": sorted(files)})

        elif name == "read_file":
            path = input_data.get("path", "")
            file_path = skill_dir / path

            if not file_path.exists() or not file_path.is_file():
                return json.dumps({"error": f"File not found: {path}"})

            # Security: prevent path traversal
            try:
                file_path.resolve().relative_to(skill_dir.resolve())
            except ValueError:
                return json.dumps({"error": f"Access denied: {path}"})

            content = file_path.read_text(encoding="utf-8")
            return json.dumps({"content": content, "path": path})

        elif name == "extract_skill":
            # Validate the extraction data
            ExtractedSkill.model_validate(input_data)
            return json.dumps({"status": "success", "message": "Skill extracted successfully"})

        else:
            return json.dumps({"error": f"Unknown tool: {name}"})

    except Exception as e:
        logger.error(f"Tool execution error: {e}")
        return json.dumps({"error": str(e)})


def tool_use_loop(
    skill_dir: Path,
    skill_hash: str,
    skill_id: str,
    parent_context: dict | None = None,
    skill_registry: "SkillRegistry | None" = None,
    preloaded_content: str | None = None,
    preloaded_file_tree: str | None = None,
    content_extraction: "ContentExtraction | None" = None,
) -> ExtractedSkill:
    """
    Orchestrates the tool-use conversation with Claude.

    Args:
        skill_dir: Path to skill directory
        skill_hash: Pre-computed SHA-256 hash of skill files
        skill_id: Pre-computed skill ID slug
        parent_context: Optional context for sub-skill extraction containing:
            - filename: The markdown filename being extracted
            - parent_skill_id: The Qualified ID of the parent skill
            - sibling_names: List of sibling sub-skill filenames
        skill_registry: Optional SkillRegistry for known-skills context
        preloaded_content: Optional SKILL.md content to inject directly
        preloaded_file_tree: Optional file tree string to include
        content_extraction: Optional pre-parsed content blocks for LLM annotation

    Returns:
        ExtractedSkill with structured data

    Raises:
        ExtractionError: If extraction fails or times out
    """
    # Build system prompt with optional context augmentation
    system_prompt = SYSTEM_PROMPT
    if skill_registry:
        system_prompt = system_prompt + skill_registry.build_llm_context_section()
    if parent_context:
        context_augmentation = build_sub_skill_context_prompt(
            filename=parent_context.get("filename", "unknown.md"),
            parent_skill_id=parent_context.get("parent_skill_id", ""),
            sibling_names=parent_context.get("sibling_names")
        )
        system_prompt = system_prompt + context_augmentation

    # Build user message — direct content injection or tool-use discovery
    if preloaded_content:
        content_parts = [f"""Analyze the following skill and extract its structure.

Skill ID: {skill_id}
Content Hash: {skill_hash[:16]}...

## FILE TREE

```
{preloaded_file_tree or '(not available)'}
```

## SKILL CONTENT

{preloaded_content}

---

Submit your extraction using the extract_skill tool."""]
    else:
        content_parts = [f"""Analyze the skill in this directory and extract its structure.

Directory: {skill_dir.name}
Skill ID: {skill_id}
Content Hash: {skill_hash[:16]}...

Use the available tools to:
1. List and read the skill files
2. Extract the structured data
3. Submit with extract_skill"""]

    # Inject pre-extracted content block summaries for LLM annotation
    if content_extraction:
        import json as _json
        content_summary_parts = ["\n\n## PRE-EXTRACTED CONTENT BLOCKS\n"]

        if content_extraction.code_blocks:
            blocks_summary = [
                {"index": i, "language": b.language, "lines": f"{b.source_line_start}-{b.source_line_end}"}
                for i, b in enumerate(content_extraction.code_blocks)
            ]
            content_summary_parts.append(
                f"### Code Blocks ({len(content_extraction.code_blocks)} found)\n"
                f"{_json.dumps(blocks_summary)}\n"
            )

        if content_extraction.tables:
            tables_summary = [
                {"index": i, "rows": t.row_count, "caption": t.caption}
                for i, t in enumerate(content_extraction.tables)
            ]
            content_summary_parts.append(
                f"### Tables ({len(content_extraction.tables)} found)\n"
                f"{_json.dumps(tables_summary)}\n"
            )

        if content_extraction.flowcharts:
            flow_summary = [
                {"index": i, "type": f.chart_type}
                for i, f in enumerate(content_extraction.flowcharts)
            ]
            content_summary_parts.append(
                f"### Flowcharts ({len(content_extraction.flowcharts)} found)\n"
                f"{_json.dumps(flow_summary)}\n"
            )

        if content_extraction.procedures:
            proc_summary = [
                {"index": i, "steps": len(p.items)}
                for i, p in enumerate(content_extraction.procedures)
            ]
            content_summary_parts.append(
                f"### Ordered Procedures ({len(content_extraction.procedures)} found)\n"
                f"{_json.dumps(proc_summary)}\n"
            )

        if content_extraction.templates:
            tmpl_summary = [
                {"index": i, "variables": t.detected_variables}
                for i, t in enumerate(content_extraction.templates)
            ]
            content_summary_parts.append(
                f"### Templates ({len(content_extraction.templates)} found)\n"
                f"{_json.dumps(tmpl_summary)}\n"
            )

        content_parts[0] += "".join(content_summary_parts)

    messages = [{
        "role": "user",
        "content": content_parts[0]
    }]

    for iteration in range(MAX_ITERATIONS):
        logger.debug(f"Tool-use iteration {iteration + 1}/{MAX_ITERATIONS}")

        try:
            response = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=8192,
                tools=TOOLS,
                messages=messages,
                system=system_prompt,
                timeout=EXTRACTION_TIMEOUT
            )
        except anthropic.APIError as e:
            raise ExtractionError(f"API error during extraction: {e}")

        # Process response blocks
        tool_results = []
        _extraction_data = None  # Use underscore prefix for internal use

        for block in response.content:
            if block.type == "tool_use":
                logger.debug(f"Tool call: {block.name}")

                if block.name == COMPLETION_TOOL:
                    # Validate and return the extraction
                    try:
                        skill = ExtractedSkill.model_validate(block.input)
                        # Override with our computed values
                        skill.id = skill_id
                        skill.hash = skill_hash
                        skill.provenance = str(skill_dir)
                        skill.generated_by = ANTHROPIC_MODEL
                        logger.info(f"Successfully extracted skill: {skill_id}")
                        return skill
                    except Exception as e:
                        raise ExtractionError(f"Invalid extraction data: {e}")
                else:
                    # Execute tool and collect result
                    result = execute_tool(block.name, block.input, skill_dir)
                    tool_results.append(tool_result(block.id, result))

            elif block.type == "text":
                logger.debug(f"LLM text: {block.text[:100]}...")

        # Check for end_turn without extraction
        if response.stop_reason == "end_turn":
            raise ExtractionError("LLM finished without calling extract_skill")

        # Add tool results to conversation
        if tool_results:
            messages.extend(tool_results)

    raise ExtractionError(f"Max iterations ({MAX_ITERATIONS}) exceeded")


# ============================================================================
# DocGraph v2: Skeleton Hydration (Phase 1c)
# ============================================================================

def hydrate_skeleton(
    skeleton: "DocumentSkeleton",
    blocks_index: dict[str, "FlatBlock"],
    markdown: str | None = None,
) -> list["Section"]:
    """Hydrate a document skeleton with real Pydantic objects.

    Phase 1c: replaces block_ids in skeleton with actual content from Phase 1a.
    Falls back to v1 deterministic tree builder if skeleton is empty.
    """
    from compiler.schemas import Section

    if not skeleton.sections and markdown:
        # Fallback to v1 builder
        from compiler.content_parser import extract_structural_content
        result = extract_structural_content(markdown)
        return result.sections

    sections = []
    section_order = 0

    for node in skeleton.sections:
        block = blocks_index.get(node.block_id)
        if block is None:
            continue

        if block.block_type == "heading":
            section_order += 1
            section = Section(
                title=block.content.text,
                level=block.content.level,
                order=section_order,
            )
            _hydrate_children(section, node, blocks_index)
            sections.append(section)
        elif block.block_type == "frontmatter":
            # Frontmatter as preamble section
            section = Section(title="", level=0, order=0)
            section.content.append(block.content)
            _hydrate_children(section, node, blocks_index)
            sections.append(section)
        else:
            # Non-heading root — create anonymous section
            section_order += 1
            section = Section(title="", level=0, order=section_order)
            section.content.append(block.content)
            _hydrate_children(section, node, blocks_index)
            sections.append(section)

    return sections


def _hydrate_children(section, node, blocks_index):
    """Recursively hydrate children of a skeleton node into a section."""
    from compiler.schemas import Section

    for child_node in node.children:
        block = blocks_index.get(child_node.block_id)
        if block is None:
            continue

        if block.block_type == "heading":
            # Subsection
            sub = Section(
                title=block.content.text,
                level=block.content.level,
                order=len(section.subsections) + 1,
            )
            _hydrate_children(sub, child_node, blocks_index)
            section.subsections.append(sub)
        else:
            section.content.append(block.content)
            _hydrate_children(section, child_node, blocks_index)
