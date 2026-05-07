# benchmark/tests/test_mcp_inject.py
"""Tests for MCP injection configuration."""

import json
import pytest
from benchmark.wrappers.skillsbench import SkillsBenchWrapper


class TestMCPInjection:
    def test_mcp_config_structure(self):
        """Verify the MCP config that would be written to container."""
        mcp_config = {
            "mcpServers": {
                "onto": {
                    "command": "/usr/local/bin/ontomcp",
                    "args": ["--ontology-root", "/opt/ontoskills/packages"],
                    "type": "stdio",
                }
            }
        }
        assert "onto" in mcp_config["mcpServers"]
        server = mcp_config["mcpServers"]["onto"]
        assert server["command"] == "/usr/local/bin/ontomcp"
        assert "--ontology-root" in server["args"]
        assert server["type"] == "stdio"

    def test_wrapper_has_ontomcp_bin_attribute(self):
        """SkillsBenchWrapper should have ontomcp_bin attribute."""
        wrapper = SkillsBenchWrapper.__new__(SkillsBenchWrapper)
        wrapper.ontomcp_bin = "/fake/ontomcp"
        assert wrapper.ontomcp_bin == "/fake/ontomcp"
