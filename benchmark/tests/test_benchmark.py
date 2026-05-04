"""Unit tests for the OntoSkills benchmark framework.

All external dependencies (Anthropic API, ontomcp subprocess, rdflib, tau2_bench)
are mocked. Tests run without ANTHROPIC_API_KEY, without the ontomcp binary,
and without any installed benchmark datasets.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest


# =====================================================================
# Helpers
# =====================================================================

def make_mock_proc(request_response_map):
    """Create a mock subprocess that responds to specific requests.

    *request_response_map* is a list of response dicts returned in order.
    """
    proc = MagicMock()
    responses = iter(request_response_map)

    def mock_readline():
        try:
            return json.dumps(next(responses)).encode() + b"\n"
        except StopIteration:
            return b""

    proc.stdout.readline = mock_readline
    proc.poll.return_value = None
    return proc


def _make_anthropic_text_response(text="answer", input_tokens=100, output_tokens=50, stop_reason="end_turn"):
    """Build a mock Anthropic response with only text content."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    resp.usage = MagicMock(input_tokens=input_tokens, output_tokens=output_tokens)
    resp.stop_reason = stop_reason
    return resp


def _make_anthropic_tool_response(tool_name, tool_input, tool_id="tool_1",
                                   input_tokens=100, output_tokens=50):
    """Build a mock Anthropic response with a tool_use block."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = ""

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = tool_id
    tool_block.name = tool_name
    tool_block.input = tool_input

    resp = MagicMock()
    resp.content = [text_block, tool_block]
    resp.usage = MagicMock(input_tokens=input_tokens, output_tokens=output_tokens)
    resp.stop_reason = "tool_use"
    return resp


# =====================================================================
# Group 1: MCP Client
# =====================================================================

class TestMCPClient:
    """Tests for benchmark.mcp_client.client.MCPClient."""

    def test_mcp_client_send_request_frames_jsonrpc(self):
        """_send_request writes a JSON line with correct jsonrpc/method/id and reads a response."""
        response = {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
        proc = make_mock_proc([response])
        proc.stdin = MagicMock()

        with patch("benchmark.mcp_client.client.MCPClient.start"):
            from benchmark.mcp_client.client import MCPClient
            client = MCPClient(ontology_root="/tmp/fake")
            client._proc = proc

            # Patch _readline_with_timeout to read from the mock
            with patch.object(client, "_readline_with_timeout", return_value=json.dumps(response).encode() + b"\n"):
                result = client._send_request("some_method", {"key": "val"})

        # Verify the request was written
        proc.stdin.write.assert_called_once()
        written = proc.stdin.write.call_args[0][0]
        parsed = json.loads(written.decode("utf-8"))
        assert parsed["jsonrpc"] == "2.0"
        assert parsed["method"] == "some_method"
        assert parsed["id"] == 1
        assert parsed["params"] == {"key": "val"}
        assert result == response

    def test_mcp_client_call_tool(self):
        """call_tool sends tools/call with correct name/arguments."""
        response = {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": "ok"}]}}
        proc = make_mock_proc([response])
        proc.stdin = MagicMock()

        with patch("benchmark.mcp_client.client.MCPClient.start"):
            from benchmark.mcp_client.client import MCPClient
            client = MCPClient(ontology_root="/tmp/fake")
            client._proc = proc

            with patch.object(client, "_readline_with_timeout", return_value=json.dumps(response).encode() + b"\n"):
                result = client.call_tool("ontoskill", {"query": "create pdf"})

        written = proc.stdin.write.call_args[0][0]
        parsed = json.loads(written.decode("utf-8"))
        assert parsed["method"] == "tools/call"
        assert parsed["params"]["name"] == "ontoskill"
        assert parsed["params"]["arguments"] == {"query": "create pdf"}
        assert result == {"content": [{"type": "text", "text": "ok"}]}

    def test_mcp_client_initialize(self):
        """initialize sends the right method and fires notifications/initialized."""
        init_response = {
            "jsonrpc": "2.0", "id": 1,
            "result": {
                "protocolVersion": "2025-11-25",
                "serverInfo": {"name": "ontomcp", "version": "0.1.0"},
            },
        }
        proc = make_mock_proc([init_response])
        proc.stdin = MagicMock()

        with patch("benchmark.mcp_client.client.MCPClient.start"):
            from benchmark.mcp_client.client import MCPClient
            client = MCPClient(ontology_root="/tmp/fake")
            client._proc = proc

            with patch.object(client, "_readline_with_timeout", return_value=json.dumps(init_response).encode() + b"\n"):
                with patch.object(client, "_send_notification") as mock_notify:
                    caps = client.initialize()

        # Verify the request was correct
        written = proc.stdin.write.call_args[0][0]
        parsed = json.loads(written.decode("utf-8"))
        assert parsed["method"] == "initialize"
        assert parsed["params"]["protocolVersion"] == "2025-11-25"
        assert parsed["params"]["clientInfo"]["name"] == "ontoskills-benchmark"

        # Verify the initialized notification was sent
        mock_notify.assert_called_once_with("notifications/initialized")
        assert client._initialized is True
        assert caps["serverInfo"]["name"] == "ontomcp"

    def test_mcp_client_close_terminates(self):
        """close() calls proc.terminate()."""
        proc = MagicMock()
        proc.stdin = MagicMock()
        proc.poll.return_value = None
        proc.returncode = 0

        with patch("benchmark.mcp_client.client.MCPClient.start"):
            from benchmark.mcp_client.client import MCPClient
            client = MCPClient(ontology_root="/tmp/fake")
            client._proc = proc
            client.close()

        proc.stdin.close.assert_called_once()
        proc.terminate.assert_called_once()
        assert client._proc is None


# =====================================================================
# Group 2: Agent dispatch
# =====================================================================

class TestAgentDispatch:
    """Tests for TraditionalAgent and OntoSkillsAgent."""

    def test_traditional_agent_single_turn(self):
        """TraditionalAgent.run() returns AgentResult with text, turns=1, tool_calls=0."""
        mock_response = _make_anthropic_text_response("The answer is 42.")

        with patch("benchmark.agents.base.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = mock_response
            MockClient.return_value.count_tokens.return_value = 50

            # Patch _load_skill_registry to return empty registry (no skills dir needed)
            with patch("benchmark.agents.traditional._load_skill_registry", return_value=("", {})):
                from benchmark.agents.traditional import TraditionalAgent
                agent = TraditionalAgent(model="claude-sonnet-4-6", skills_dir="/tmp/nonexistent", api_key="test-key")
                result = agent.run("What is 6*7?")

        assert result.answer == "The answer is 42."
        assert result.turns == 1
        assert result.tool_calls == 0
        assert result.input_tokens == 100
        assert result.output_tokens == 50

    def test_traditional_agent_ignores_tool_use(self):
        """TraditionalAgent.run() raises when model emits tool_use without tool_result."""
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Here is my answer."

        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.id = "tool_abc"
        tool_block.name = "ontoskill"
        tool_block.input = {"query": "test"}

        mock_response = MagicMock()
        mock_response.content = [text_block, tool_block]
        mock_response.usage = MagicMock(input_tokens=80, output_tokens=30)
        mock_response.stop_reason = "tool_use"

        with patch("benchmark.agents.base.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = mock_response
            MockClient.return_value.count_tokens.return_value = 50

            with patch("benchmark.agents.traditional._load_skill_registry", return_value=("", {})):
                from benchmark.agents.traditional import TraditionalAgent
                agent = TraditionalAgent(model="claude-sonnet-4-6", skills_dir="/tmp/nonexistent", api_key="test-key")
                with pytest.raises(RuntimeError, match="Missing tool_result"):
                    agent.run("Do something")

    def test_ontoskills_agent_tool_dispatch(self):
        """OntoSkillsAgent dispatches tool_use to MCP client and sends back tool_result."""
        tool_response = _make_anthropic_tool_response("ontoskill", {"query": "pdf"}, tool_id="t1")

        # Second response: the final text answer after tool result
        final_response = _make_anthropic_text_response("Found skill: create_pdf")

        mock_mcp_result = {"content": [{"type": "text", "text": "create_pdf skill found"}]}

        with patch("benchmark.agents.base.anthropic.Anthropic") as MockClient:
            # First call returns tool_use, second returns final text
            MockClient.return_value.messages.create.side_effect = [tool_response, final_response]

            with patch("benchmark.agents.ontoskills.MCPClient") as MockMCP:
                mock_client_instance = MagicMock()
                mock_client_instance.call_tool.return_value = mock_mcp_result
                mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
                mock_client_instance.__exit__ = MagicMock(return_value=False)
                MockMCP.return_value = mock_client_instance

                from benchmark.agents.ontoskills import OntoSkillsAgent
                agent = OntoSkillsAgent(
                    model="claude-sonnet-4-6",
                    ontology_root="/tmp/fake",
                    api_key="test-key",
                )
                result = agent.run("How to create a PDF?")

        # MCP tool was called
        mock_client_instance.call_tool.assert_called_once_with("ontoskill", {"query": "pdf"})
        # Result should contain the final answer
        assert "Found skill: create_pdf" in result.answer
        assert result.tool_calls == 1
        assert result.turns == 2  # first turn (tool_use) + second turn (answer)

    def test_ontoskills_agent_subprocess_crash(self):
        """Agent handles MCP subprocess crash gracefully."""
        tool_response = _make_anthropic_tool_response("ontoskill", {"query": "pdf"}, tool_id="t1")

        with patch("benchmark.agents.base.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = tool_response

            with patch("benchmark.agents.ontoskills.MCPClient") as MockMCP:
                mock_client_instance = MagicMock()
                mock_client_instance.call_tool.side_effect = RuntimeError("Connection lost")
                # Simulate dead subprocess
                mock_proc = MagicMock()
                mock_proc.poll.return_value = 1  # non-None = dead
                mock_client_instance._proc = mock_proc
                mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
                mock_client_instance.__exit__ = MagicMock(return_value=False)
                MockMCP.return_value = mock_client_instance

                from benchmark.agents.ontoskills import OntoSkillsAgent
                agent = OntoSkillsAgent(
                    model="claude-sonnet-4-6",
                    ontology_root="/tmp/fake",
                    api_key="test-key",
                )
                result = agent.run("How to create a PDF?")

        # Should not crash; should have recorded tool_call but broken out of the loop
        assert result.tool_calls == 1
        assert result.turns == 1


# =====================================================================
# Group 3: Patch extraction
# =====================================================================

class TestPatchExtraction:
    """Tests for SWEBenchWrapper.extract_patch_from_answer."""

    def test_extract_patch_fenced_diff(self):
        """Extract patch from a ```diff ... ``` fenced block."""
        from benchmark.wrappers.swebench import SWEBenchWrapper

        answer = (
            "Here is the fix:\n\n"
            "```diff\n"
            "--- a/file.py\n"
            "+++ b/file.py\n"
            "@@ -1,3 +1,3 @@\n"
            "-old line\n"
            "+new line\n"
            " context\n"
            "```\n"
        )
        result = SWEBenchWrapper.extract_patch_from_answer(answer)
        assert "--- a/file.py" in result
        assert "+++ b/file.py" in result
        assert "-old line" in result
        assert "+new line" in result

    def test_extract_patch_git_diff(self):
        """Extract patch from a bare diff --git block with hunk lines."""
        from benchmark.wrappers.swebench import SWEBenchWrapper

        # The _PLAIN_DIFF_RE captures lines starting with space/tab/+/-.
        # It stops at a line that starts with a non-diff character.
        answer = (
            "Some text before\n"
            "diff --git a/file.py b/file.py\n"
            "--- a/file.py\n"
            "+++ b/file.py\n"
            " context\n"
            "-old\n"
            "+new\n"
        )
        result = SWEBenchWrapper.extract_patch_from_answer(answer)
        assert "diff --git a/file.py b/file.py" in result
        assert "-old" in result
        assert "+new" in result

    def test_extract_patch_no_diff(self):
        """Return empty string when answer has no diff."""
        from benchmark.wrappers.swebench import SWEBenchWrapper

        answer = "I cannot produce a patch for this issue."
        result = SWEBenchWrapper.extract_patch_from_answer(answer)
        assert result == ""


# =====================================================================
# Group 4: Metrics computation
# =====================================================================

class TestMetrics:
    """Tests for benchmark.reporting.metrics."""

    @staticmethod
    def _make_result(input_tokens, output_tokens, latency_ms=100.0,
                     tool_calls=0, turns=1):
        """Create a mock AgentResult-like object for metrics tests."""
        m = MagicMock()
        m.input_tokens = input_tokens
        m.output_tokens = output_tokens
        m.total_latency_ms = latency_ms
        m.tool_calls = tool_calls
        m.turns = turns
        return {"task_id": "t1", "model_answer": "a", "metrics": m}

    def test_compute_agent_metrics_basic(self):
        """Feed 3 results with known metrics; verify averages are correct."""
        from benchmark.reporting.metrics import compute_agent_metrics

        results = [
            self._make_result(100, 50, latency_ms=200.0, tool_calls=1, turns=1),
            self._make_result(200, 100, latency_ms=400.0, tool_calls=2, turns=2),
            self._make_result(300, 150, latency_ms=600.0, tool_calls=3, turns=3),
        ]

        metrics = compute_agent_metrics("traditional", "gaia", results, accuracy=0.66)

        assert metrics.num_tasks == 3
        assert metrics.accuracy == 0.66
        assert metrics.avg_input_tokens == 200.0  # (100+200+300)/3
        assert metrics.avg_output_tokens == 100.0  # (50+100+150)/3
        assert metrics.avg_total_tokens == 300.0  # (150+300+450)/3
        assert metrics.avg_latency_ms == 400.0  # (200+400+600)/3
        assert metrics.avg_tool_calls == 2.0  # (1+2+3)/3
        assert metrics.avg_turns == 2.0  # (1+2+3)/3

    def test_compute_agent_metrics_empty(self):
        """Empty results list returns zeroed metrics."""
        from benchmark.reporting.metrics import compute_agent_metrics

        metrics = compute_agent_metrics("traditional", "gaia", [])

        assert metrics.num_tasks == 0
        assert metrics.avg_input_tokens == 0.0
        assert metrics.avg_output_tokens == 0.0
        assert metrics.avg_total_tokens == 0.0
        assert metrics.avg_latency_ms == 0.0
        assert metrics.avg_tool_calls == 0.0
        assert metrics.avg_turns == 0.0

    def test_compute_comparison(self):
        """Traditional has 100 tokens, OntoSkills has 40; token_reduction_pct is ~60%."""
        from benchmark.reporting.metrics import compute_comparison

        trad_results = {
            "gaia": [self._make_result(80, 20, turns=1)],
        }
        os_results = {
            "gaia": [self._make_result(30, 10, turns=1)],
        }

        report = compute_comparison(trad_results, os_results)

        assert len(report.comparisons) == 1
        comp = report.comparisons[0]
        assert comp.benchmark == "gaia"
        assert comp.traditional is not None
        assert comp.ontoskills is not None
        assert comp.token_reduction_pct is not None
        # Traditional total: 100, OntoSkills total: 40 => (100-40)/100 * 100 = 60%
        assert abs(comp.token_reduction_pct - 60.0) < 0.01

    def test_fmt_us_fmt_usd(self):
        """Formatting helpers produce expected strings."""
        from benchmark.reporting.comparison import fmt_us, fmt_usd

        # Microseconds (source uses Greek mu U+03BC)
        assert fmt_us(500) == "500μs"
        assert fmt_us(1500) == "2ms"
        assert fmt_us(2_500_000) == "2.5s"

        # USD
        assert fmt_usd(0.0005) == "$0.000500"
        assert fmt_usd(0.05) == "$0.0500"
        assert fmt_usd(12.50) == "$12.50"


# =====================================================================
# Group 5: Content coverage
# =====================================================================

class TestContentCoverage:
    """Tests for benchmark.content_coverage line-coverage and knowledge-yield."""

    def test_calc_line_coverage_full(self):
        """All lines covered -> 100%."""
        from benchmark.content_coverage import calc_line_coverage

        md = "line 1\nline 2\nline 3\n"

        # FlatBlock-like objects with line_start and line_end
        Block = lambda **kw: type("B", (), kw)  # simple namespace factory
        blocks = [
            Block(line_start=1, line_end=4),  # covers lines 1-3
        ]
        assert calc_line_coverage(md, blocks) == 100.0

    def test_calc_line_coverage_partial(self):
        """Some lines uncovered -> correct percentage."""
        from benchmark.content_coverage import calc_line_coverage

        md = "line 1\nline 2\nline 3\nline 4\nline 5\n"

        Block = lambda **kw: type("B", (), kw)
        blocks = [
            Block(line_start=1, line_end=1),  # range(0, 1) -> only index 0
        ]
        # 5 non-blank lines, 1 covered => 20%
        result = calc_line_coverage(md, blocks)
        assert abs(result - 20.0) < 0.01

    def test_knowledge_yield_parse(self):
        """Mock rdflib Graph to return known SPARQL results; verify dimension/type counts."""
        # Mock SPARQL result rows
        epistemic_rows = [
            MagicMock(dimension="https://ontoskills.sh/ontology#Observability", cnt=5),
            MagicMock(dimension="https://ontoskills.sh/ontology#ResilienceTactic", cnt=3),
        ]
        operational_rows = [
            MagicMock(otype="https://ontoskills.sh/ontology#Procedure", cnt=10),
            MagicMock(otype="https://ontoskills.sh/ontology#CodePattern", cnt=4),
        ]

        mock_graph = MagicMock()
        mock_graph.query.side_effect = [epistemic_rows, operational_rows]

        mock_rdflib_module = MagicMock()
        mock_rdflib_module.Graph.return_value = mock_graph

        from pathlib import Path

        with patch.dict("sys.modules", {"rdflib": mock_rdflib_module, "rdflib.Graph": mock_rdflib_module.Graph}):
            with patch("benchmark.content_coverage.Path.rglob") as mock_rglob:
                # Return one fake TTL file (not core.ttl)
                mock_file = MagicMock()
                mock_file.name = "skill1.ttl"
                mock_file.__str__ = lambda self: "/tmp/skill1.ttl"
                mock_rglob.return_value = [mock_file]

                from benchmark.content_coverage import compute_knowledge_yield
                result = compute_knowledge_yield(Path("/tmp/fake_ttl"))

        assert result["total_epistemic"] == 8  # 5 + 3
        assert result["total_operational"] == 14  # 10 + 4
        assert result["skills_analyzed"] == 1
        assert result["epistemic_distribution"]["Observability"] == 5
        assert result["epistemic_distribution"]["ResilienceTactic"] == 3
        # Other dimensions should be zero-filled
        assert result["epistemic_distribution"]["TrustMetric"] == 0
        assert result["type_distribution"]["Procedure"] == 10
        assert result["type_distribution"]["CodePattern"] == 4

    def test_knowledge_yield_empty(self):
        """Empty directory returns zeroed counts."""
        from pathlib import Path

        with patch("benchmark.content_coverage.Path.rglob", return_value=[]):
            from benchmark.content_coverage import compute_knowledge_yield
            result = compute_knowledge_yield(Path("/tmp/empty"))

        assert result["skills_analyzed"] == 0
        assert result["total_epistemic"] == 0
        assert result["total_operational"] == 0
        assert result["avg_operational_per_skill"] == 0.0
        assert result["operational_density"] == 0.0
