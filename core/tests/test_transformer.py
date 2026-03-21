import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from compiler.transformer import (
    tool_result,
    execute_tool,
    tool_use_loop,
    TOOLS,
)
from compiler.config import MAX_ITERATIONS
from compiler.schemas import ExtractedSkill, Requirement, ExecutionPayload


def test_tools_defined():
    """Test that all required tools are defined."""
    tool_names = [t["name"] for t in TOOLS]
    assert "list_files" in tool_names
    assert "read_file" in tool_names
    assert "extract_skill" in tool_names


def test_tool_result():
    """Test tool result message creation."""
    result = tool_result("tool_123", '{"files": ["SKILL.md"]}')
    assert result["role"] == "user"
    assert result["content"][0]["type"] == "tool_result"
    assert result["content"][0]["tool_use_id"] == "tool_123"
    assert result["content"][0]["content"] == '{"files": ["SKILL.md"]}'


def test_execute_tool_list_files(tmp_path):
    """Test list_files tool execution."""
    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# Test Skill")
    (skill_dir / "references").mkdir()
    (skill_dir / "references" / "guide.md").write_text("Guide")

    import json
    result = execute_tool("list_files", {}, skill_dir)
    data = json.loads(result)
    assert "SKILL.md" in data["files"]
    assert "references/guide.md" in data["files"]


def test_execute_tool_read_file(tmp_path):
    """Test read_file tool execution."""
    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# Test Skill\n\nContent here")

    import json
    result = execute_tool("read_file", {"path": "SKILL.md"}, skill_dir)
    data = json.loads(result)
    assert data["content"] == "# Test Skill\n\nContent here"
    assert data["path"] == "SKILL.md"


def test_execute_tool_read_file_not_found(tmp_path):
    """Test read_file tool with non-existent file."""
    import json
    result = execute_tool("read_file", {"path": "nonexistent.md"}, tmp_path)
    data = json.loads(result)
    assert "error" in data


def test_execute_tool_extract_skill(tmp_path):
    """Test extract_skill tool returns success."""
    import json
    extraction_data = {
        "id": "test-skill",
        "hash": "abc123",
        "nature": "A test skill",
        "genus": "Test",
        "differentia": "for testing",
        "intents": ["testing"],
        "requirements": [],
        "constraints": [],
        "execution_payload": None,
        "provenance": None,
    }
    result = execute_tool("extract_skill", extraction_data, tmp_path)
    data = json.loads(result)
    assert data["status"] == "success"


@patch("compiler.transformer.client")
def test_tool_use_loop_success(mock_client, tmp_path):
    """Test successful tool-use loop."""
    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# Test")

    # Mock the API response sequence
    list_response = MagicMock()
    list_response.content = [MagicMock(type="tool_use", name="list_files", id="t1")]
    list_response.stop_reason = "tool_use"

    read_response = MagicMock()
    read_response.content = [MagicMock(type="tool_use", name="read_file", id="t2", input={"path": "SKILL.md"})]
    read_response.stop_reason = "tool_use"

    extract_response = MagicMock()
    extract_block = MagicMock()
    extract_block.type = "tool_use"
    extract_block.name = "extract_skill"
    extract_block.input = {
        "id": "test-skill",
        "hash": "abc123",
        "nature": "Test",
        "genus": "Test",
        "differentia": "test",
        "intents": ["test"],
        "requirements": [],
        "constraints": [],
        "execution_payload": None,
        "provenance": None,
    }
    extract_response.content = [extract_block]
    extract_response.stop_reason = "tool_use"

    mock_client.messages.create.side_effect = [list_response, read_response, extract_response]

    result = tool_use_loop(skill_dir, "abc123hash", "test-skill")
    assert isinstance(result, ExtractedSkill)
    assert result.id == "test-skill"


def test_system_prompt_includes_state_extraction():
    """Test that SYSTEM_PROMPT includes state transition extraction instructions."""
    from transformer import SYSTEM_PROMPT
    assert "STATE TRANSITION EXTRACTION" in SYSTEM_PROMPT
    assert "requiresState" in SYSTEM_PROMPT
    assert "yieldsState" in SYSTEM_PROMPT
    assert "handlesFailure" in SYSTEM_PROMPT
    assert "oc:SystemAuthenticated" in SYSTEM_PROMPT
    assert "oc:PermissionDenied" in SYSTEM_PROMPT
    assert "URIs" in SYSTEM_PROMPT


@patch("compiler.transformer.client")
def test_tool_use_loop_sets_generated_by(mock_client, tmp_path):
    """Test that tool_use_loop sets generated_by field."""
    from config import ANTHROPIC_MODEL

    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# Test")

    extract_response = MagicMock()
    extract_block = MagicMock()
    extract_block.type = "tool_use"
    extract_block.name = "extract_skill"
    extract_block.input = {
        "id": "test-skill",
        "hash": "abc123",
        "nature": "Test",
        "genus": "Test",
        "differentia": "test",
        "intents": ["test"],
        "requirements": [],
        "constraints": [],
        "execution_payload": None,
        "provenance": None,
    }
    extract_response.content = [extract_block]
    extract_response.stop_reason = "tool_use"

    mock_client.messages.create.return_value = extract_response

    result = tool_use_loop(skill_dir, "abc123hash", "test-skill")
    assert result.generated_by == ANTHROPIC_MODEL

