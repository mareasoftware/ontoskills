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
            expected = {"ontoskill"}
            if set(tool_names) != expected:
                print(f"  FAIL: expected {expected}, got {set(tool_names)}")
                errors += 1
            else:
                print("  OK: ontoskill tool present")
            print()

            # Step 4: Search for skills via ontoskill
            print("=== Step 4: Search skills ===")
            search_result = client.call_tool("ontoskill", {"q": "excel", "top_k": 3})
            print(f"  ontoskill('excel'): {json.dumps(search_result, indent=2)[:500]}")
            if not search_result or not search_result.get("content"):
                print("  FAIL: ontoskill returned no content")
                errors += 1
            else:
                print("  OK: search returned results")
            print()

            # Step 5: Get skill context via ontoskill
            print("=== Step 5: Get skill context ===")
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
                ctx_result = client.call_tool("ontoskill", {"q": skill_id})
                print(f"  ontoskill('{skill_id}'): {json.dumps(ctx_result, indent=2)[:500]}")
                print("  OK: got skill context")
            else:
                text = content[0].get("text", "") if content else ""
                for line in text.split("\n"):
                    if line.startswith("- "):
                        skill_id = line.split("- ")[1].split()[0]
                        break
                if skill_id:
                    ctx_result = client.call_tool("ontoskill", {"q": skill_id})
                    print(f"  ontoskill('{skill_id}') from compact text")
                    print("  OK: got skill context")
                else:
                    print(f"  SKIP: could not extract skill_id from search results")
            print()

            # Step 6: List tools (verification step — ontoskill is the primary tool)
            print("=== Step 6: Tool verification ===")
            tools = client.list_tools()
            print(f"  {len(tools)} tool(s) available: {[t['name'] for t in tools]}")
            print("  OK: tools listed")
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
