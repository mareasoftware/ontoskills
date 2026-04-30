"""Tests for the unified ontoskill tool and skill_hints flag."""

import json
import pytest


def test_tool_definitions_single_tool():
    """OntoSkillsAgent exposes only 1 tool: ontoskill."""
    from benchmark.agents.ontoskills import _TOOL_DEFINITIONS

    assert len(_TOOL_DEFINITIONS) == 1
    assert _TOOL_DEFINITIONS[0]["name"] == "ontoskill"
    schema = _TOOL_DEFINITIONS[0]["input_schema"]
    assert "q" in schema["properties"]
    assert "top_k" in schema["properties"]
    assert schema["required"] == ["q"]


def test_tool_schema_compact():
    """ontoskill schema should be compact (under 500 chars / ~125 tokens)."""
    from benchmark.agents.ontoskills import _TOOL_DEFINITIONS

    schema_json = json.dumps(_TOOL_DEFINITIONS)
    assert len(schema_json) < 500


def test_skill_hints_flag_in_prompt():
    """With skill_hints=False, prompt should not contain skill names."""
    from benchmark.wrappers.skillsbench import SkillsBenchWrapper

    wrapper = SkillsBenchWrapper.__new__(SkillsBenchWrapper)
    wrapper.repo_path = None
    wrapper.tasks_dir = None

    task = {
        "instruction": "Calculate distance",
        "dockerfile": "FROM python:3.12",
        "test_content": "",
        "skill_ids": ["geospatial-analysis"],
        "skills_content": {},
        "task_dir": "/tmp/test",
    }

    prompt_with = wrapper._build_code_gen_prompt(task, skill_hints=True)
    prompt_without = wrapper._build_code_gen_prompt(task, skill_hints=False)

    assert "geospatial-analysis" in prompt_with
    assert "geospatial-analysis" not in prompt_without
    assert "Calculate distance" in prompt_without  # instruction still present


def test_compact_tool_result_extracts_text():
    """_compact_tool_result_static extracts text from MCP response."""
    from benchmark.agents.ontoskills import OntoSkillsAgent

    mcp_result = {
        "content": [
            {"type": "text", "text": "skill knowledge here"}
        ]
    }
    result = OntoSkillsAgent._compact_tool_result_static(
        "ontoskill", {"q": "test"}, mcp_result,
    )
    assert result == "skill knowledge here"


def test_compact_tool_result_fallback_json():
    """_compact_tool_result_static falls back to JSON when no text content."""
    from benchmark.agents.ontoskills import OntoSkillsAgent

    mcp_result = {"error": "something went wrong"}
    result = OntoSkillsAgent._compact_tool_result_static(
        "ontoskill", {"q": "test"}, mcp_result,
    )
    assert "error" in result
