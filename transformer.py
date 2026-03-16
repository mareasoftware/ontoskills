"""
LLM Tool-Use Extraction Module.

Orchestrates the tool-use conversation with Claude to extract
structured skill data from markdown files.
"""

import json
import os
import logging
from pathlib import Path
from typing import Any

import anthropic
from anthropic import Anthropic

from schemas import ExtractedSkill
from exceptions import ExtractionError

logger = logging.getLogger(__name__)

# Configuration
MAX_ITERATIONS = 20
EXTRACTION_TIMEOUT = 120  # seconds per API call
COMPLETION_TOOL = "extract_skill"
MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6-20250514")

# System prompt following Knowledge Architecture framework
SYSTEM_PROMPT = """You are an Ontological Architect. Your task is to analyze agent skills
and extract their essential structure using the Knowledge Architecture framework.

## KNOWLEDGE ARCHITECTURE FRAMEWORK

### Categories of Being
- Tool: Enables action
- Concept: A framework, methodology
- Work: A created artifact generator

### Genus and Differentia
"A is a B that C" - classical definition structure

### Relations as First-Class Citizens
- depends-on: Cannot function without
- extends: Builds upon
- contradicts: In tension with
- implements: Realizes abstraction
- exemplifies: Instance of pattern

### Essential vs Accidental
Essential: Remove it → becomes something else
Accidental: Could be different without changing identity

## YOUR TASK

1. Use list_files to discover all files in the skill directory
2. Use read_file to read SKILL.md and any reference files
3. Analyze the skill and extract its structure
4. Call extract_skill with the structured data

Be thorough but concise. Focus on the essential nature of the skill."""

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


def tool_use_loop(skill_dir: Path, skill_hash: str, skill_id: str) -> ExtractedSkill:
    """
    Orchestrates the tool-use conversation with Claude.

    Args:
        skill_dir: Path to skill directory
        skill_hash: Pre-computed SHA-256 hash of skill files
        skill_id: Pre-computed skill ID slug

    Returns:
        ExtractedSkill with structured data

    Raises:
        ExtractionError: If extraction fails or times out
    """
    messages = [{
        "role": "user",
        "content": f"""Analyze the skill in this directory and extract its structure.

Directory: {skill_dir.name}
Skill ID: {skill_id}
Content Hash: {skill_hash[:16]}...

Use the available tools to:
1. List and read the skill files
2. Extract the structured data
3. Submit with extract_skill"""
    }]

    for iteration in range(MAX_ITERATIONS):
        logger.debug(f"Tool-use iteration {iteration + 1}/{MAX_ITERATIONS}")

        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=8192,
                tools=TOOLS,
                messages=messages,
                system=SYSTEM_PROMPT,
                timeout=EXTRACTION_TIMEOUT
            )
        except anthropic.APIError as e:
            raise ExtractionError(f"API error during extraction: {e}")

        # Process response blocks
        tool_results = []
        extraction_data = None

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
