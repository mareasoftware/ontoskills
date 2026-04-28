#!/usr/bin/env python3
"""Smoke test: verify ontomcp loads TTL files and responds correctly.

Usage:
    python smoketest.py [--ttl-dir <path>] [--ontomcp-bin <path>]

Exits 0 on success, 1 on failure.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Project root on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from benchmark.mcp_client.client import MCPClient
from benchmark.config import ONTOMCP_BIN_PATH, TTL_ROOT


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="OntoSkills benchmark smoke test")
    parser.add_argument("--ttl-dir", default=TTL_ROOT)
    parser.add_argument("--ontomcp-bin", default=ONTOMCP_BIN_PATH)
    args = parser.parse_args()

    ttl_dir = Path(args.ttl_dir)
    ontomcp_bin = Path(args.ontomcp_bin)

    errors = 0

    # Step 1: Check prerequisites
    print("=== Step 1: Prerequisites ===")
    if not ontomcp_bin.exists():
        print(f"FAIL: ontomcp binary not found at {ontomcp_bin}")
        return 1
    print(f"  ontomcp: {ontomcp_bin}")

    ttl_files = list(ttl_dir.rglob("*.ttl"))
    if not ttl_files:
        print(f"FAIL: No TTL files found in {ttl_dir}")
        return 1
    print(f"  TTL files: {len(ttl_files)} in {ttl_dir}")
    print()

    # Step 2: Start MCP client and initialize
    print("=== Step 2: Start ontomcp ===")
    client = MCPClient(ontomcp_bin=str(ontomcp_bin), ontology_root=str(ttl_dir))

    try:
        with client:
            init_result = client.initialize()
            print(f"  initialize: {json.dumps(init_result, indent=2)[:200]}")
            print()

            # Step 3: List tools
            print("=== Step 3: List tools ===")
            tools = client.list_tools()
            tool_names = [t["name"] for t in tools]
            print(f"  tools: {tool_names}")
            expected = {"search", "get_skill_context", "evaluate_execution_plan", "query_epistemic_rules"}
            if set(tool_names) != expected:
                print(f"  FAIL: expected {expected}, got {set(tool_names)}")
                errors += 1
            else:
                print("  OK: all 4 tools present")
            print()

            # Step 4: Search for skills
            print("=== Step 4: Search skills ===")
            search_result = client.call_tool("search", {"query": "excel", "limit": 3})
            print(f"  search('excel'): {json.dumps(search_result, indent=2)[:500]}")
            if not search_result or not search_result.get("content"):
                print("  FAIL: search returned no content")
                errors += 1
            else:
                print("  OK: search returned results")
            print()

            # Step 5: Get skill context
            print("=== Step 5: Get skill context ===")
            # Try to extract a skill ID from search results
            skill_id = None
            try:
                content = search_result.get("content", [])
                if content:
                    text = content[0].get("text", "")
                    parsed = json.loads(text)
                    if isinstance(parsed, list) and parsed:
                        skill_id = parsed[0].get("skill_id") or parsed[0].get("id")
            except (json.JSONDecodeError, IndexError, KeyError):
                pass

            if skill_id:
                ctx_result = client.call_tool("get_skill_context", {"skill_id": skill_id})
                print(f"  get_skill_context('{skill_id}'): {json.dumps(ctx_result, indent=2)[:500]}")
                print("  OK: got skill context")
            else:
                # Compact responses are text, not JSON — extract skill_id from compact text.
                text = content[0].get("text", "") if content else ""
                for line in text.split("\n"):
                    if line.startswith("- "):
                        # Compact format: "- skill_id [tier]: ..."
                        skill_id = line.split("- ")[1].split()[0]
                        break
                if skill_id:
                    ctx_result = client.call_tool("get_skill_context", {"skill_id": skill_id})
                    print(f"  get_skill_context('{skill_id}') from compact text")
                    print("  OK: got skill context")
                else:
                    print(f"  SKIP: could not extract skill_id from search results")
            print()

            # Step 6: Query epistemic rules
            print("=== Step 6: Query epistemic rules ===")
            rules_result = client.call_tool("query_epistemic_rules", {"limit": 3})
            print(f"  query_epistemic_rules(limit=3): {json.dumps(rules_result, indent=2)[:500]}")
            if rules_result and rules_result.get("content"):
                print("  OK: epistemic rules returned")
            else:
                print("  WARN: no epistemic rules found")
            print()

    except Exception as e:
        print(f"FAIL: {e}")
        import traceback
        traceback.print_exc()
        errors += 1

    # Summary
    print("=" * 40)
    if errors:
        print(f"SMOKE TEST FAILED: {errors} error(s)")
        return 1
    print("SMOKE TEST PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
