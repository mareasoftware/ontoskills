"""OntoSkills MCP client — JSON-RPC protocol handler for OntoMCP server.

The OntoMCP server speaks raw JSON-RPC over stdio (Content-Length framed
or line-delimited). This client manages the connection, request/response
lifecycle, and serialization.

Architecture:
    OntoSkillsClient → subprocess (ontomcp binary) → JSON-RPC over stdio
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

from .types import ExecutionPlan, SkillContext, SkillSearchResult

logger = logging.getLogger(__name__)

# Default locations to look for the ontomcp binary
DEFAULT_BINARY_PATHS = [
    "ontomcp",  # On PATH
    "./mcp/target/release/ontomcp",  # Built from source
    os.path.expanduser("~/.ontoskills/bin/ontomcp"),
    os.path.expanduser("~/.cargo/bin/ontomcp"),
]


class OntoSkillsError(Exception):
    """Base error for OntoSkills client operations."""


class ConnectionError(OntoSkillsError):
    """Failed to connect to OntoMCP server."""


class QueryError(OntoSkillsError):
    """A query to the ontology failed."""


class OntoSkillsClient:
    """Python client for the OntoSkills MCP server.

    Connects to an `ontomcp` binary process via stdio JSON-RPC and
    provides high-level APIs for skill search, context retrieval,
    and execution planning.

    Usage:
        client = OntoSkillsClient()
        await client.start()

        results = await client.search("how to parse PDF files")
        context = await client.get_context("pdf-generation")

        await client.stop()
    """

    def __init__(
        self,
        binary_path: Optional[str] = None,
        ontology_root: Optional[str] = None,
        timeout: float = 30.0,
    ):
        """Initialize the client.

        Args:
            binary_path: Path to the ontomcp binary. Auto-discovered if None.
            ontology_root: Path to compiled ontology directory.
            timeout: Timeout in seconds for MCP calls.
        """
        self._binary = binary_path or self._find_binary()
        self._ontology_root = ontology_root
        self._timeout = timeout
        self._process: Optional[subprocess.Popen] = None
        self._request_id: int = 0
        self._initialized: bool = False
        self._lock = asyncio.Lock()

    # ── Lifecycle ──────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the OntoMCP server process and initialize the connection."""
        if self._process is not None:
            return

        if not self._binary or not shutil.which(self._binary):
            raise ConnectionError(
                f"ontomcp binary not found. Looked in: {DEFAULT_BINARY_PATHS}\n"
                f"Build it with: cd mcp && cargo build --release"
            )

        args = [self._binary]
        if self._ontology_root:
            args.extend(["--ontology-root", self._ontology_root])

        logger.info("Starting OntoMCP: %s", " ".join(args))

        self._process = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,  # Binary mode for Content-Length framed protocol
        )

        # Send initialize request
        result = await self._request("initialize", {
            "protocolVersion": "2025-11-25",
            "clientInfo": {"name": "ontoskills-py", "version": "0.1.0"},
            "capabilities": {},
        })

        if "error" in result:
            raise ConnectionError(f"MCP initialize failed: {result['error']}")

        self._initialized = True
        logger.info("OntoMCP connected — server: %s", result.get("serverInfo", {}))

    async def stop(self) -> None:
        """Stop the OntoMCP server process."""
        if self._process is None:
            return

        logger.info("Stopping OntoMCP")
        try:
            self._process.stdin.close()
            self._process.stdout.close()
            self._process.terminate()
            self._process.wait(timeout=5)
        except Exception:
            self._process.kill()
        finally:
            self._process = None
            self._initialized = False

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *args):
        await self.stop()

    # ── Public API ─────────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[SkillSearchResult]:
        """Search for skills by natural language query or skill ID.

        If the query matches a known skill ID exactly, returns that skill's
        context directly. Otherwise performs BM25/semantic search.

        Args:
            query: Natural language query (e.g. "pdf generation") or skill ID.
            top_k: Maximum number of results.

        Returns:
            List of matching SkillSearchResult objects, best first.
        """
        result = await self._call_tool("ontoskill", {"q": query, "top_k": top_k})

        # Handle direct skill context match
        if "skill_id" in result or "knowledge_nodes" in result:
            ctx = SkillContext.from_response(result)
            return [SkillSearchResult(
                skill_id=ctx.skill_id,
                name=ctx.name,
                description=ctx.description,
                intent=ctx.intent,
                score=1.0,
            )]

        # Handle search results
        results = result.get("results", result.get("matches", []))
        return [SkillSearchResult.from_search(r) for r in results]

    async def get_context(
        self,
        skill_id: str,
        include_inherited: bool = True,
    ) -> SkillContext:
        """Get the full structured context for a skill.

        Returns all knowledge nodes, dependencies, state requirements,
        and inheritance chain for the skill.

        Args:
            skill_id: The skill identifier (e.g. "pdf-generation").
            include_inherited: Whether to include knowledge from parent skills.

        Returns:
            SkillContext with full ontology data.

        Raises:
            QueryError: If the skill is not found.
        """
        result = await self._call_tool("get_skill_context", {
            "skill_id": skill_id,
            "include_inherited_knowledge": include_inherited,
        })

        if "error" in result or "skill_id" not in result:
            raise QueryError(f"Skill not found: {skill_id}")

        return SkillContext.from_response(result)

    async def evaluate_plan(
        self,
        intent: Optional[str] = None,
        skill_id: Optional[str] = None,
        current_states: Optional[list[str]] = None,
        max_depth: int = 10,
    ) -> ExecutionPlan:
        """Evaluate which skills to execute to achieve an intent or reach a state.

        Args:
            intent: The desired intent to resolve.
            skill_id: The target skill to reach.
            current_states: Current state values the agent is in.
            max_depth: Maximum chain depth to search.

        Returns:
            ExecutionPlan with ordered skill chain.
        """
        params = {"max_depth": max_depth}
        if intent:
            params["intent"] = intent
        if skill_id:
            params["skill_id"] = skill_id
        if current_states:
            params["current_states"] = current_states

        result = await self._call_tool("evaluate_execution_plan", params)
        return ExecutionPlan.from_response(result)

    async def prefetch_knowledge(
        self,
        query: Optional[str] = None,
        skill_ids: Optional[list[str]] = None,
        max_skills: int = 3,
    ) -> list[SkillContext]:
        """Prefetch and compact context for multiple skills in one call.

        Efficient for agents that need context about several skills at once.

        Args:
            query: Natural language query to search for skills.
            skill_ids: Explicit list of skill IDs to fetch.
            max_skills: Maximum number of skills to return.

        Returns:
            List of SkillContext objects, one per matching skill.
        """
        params = {"max_skills": max_skills}
        if query:
            params["query"] = query
        if skill_ids:
            params["skill_ids"] = skill_ids

        result = await self._call_tool("prefetch_knowledge", params)
        prefetched = result.get("prefetched_skills", [])
        skill_results = result.get("results", [])

        contexts = []
        for skill_data in skill_results:
            if isinstance(skill_data, dict):
                contexts.append(SkillContext.from_response(skill_data))
        return contexts

    # ── Internal: MCP JSON-RPC protocol ────────────────────────────────

    async def _request(self, method: str, params: Optional[dict] = None) -> dict:
        """Send a JSON-RPC request and return the result."""
        async with self._lock:
            self._request_id += 1
            rid = self._request_id

            request = {
                "jsonrpc": "2.0",
                "id": rid,
                "method": method,
                "params": params or {},
            }

            return await self._send_receive(request)

    async def _call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Call an MCP tool and extract the result."""
        response = await self._request("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })

        if "error" in response:
            raise QueryError(f"Tool '{tool_name}' failed: {response['error']}")

        # Extract structured content from MCP response
        content = response.get("structuredContent", response.get("result", {}))
        if isinstance(content, dict) and "result" in content:
            content = content["result"]
        return content

    async def _send_receive(self, request: dict) -> dict:
        """Send a request to the OntoMCP process and read the response."""
        if self._process is None or self._process.stdin is None:
            raise ConnectionError("OntoMCP not started. Call start() first.")

        body = json.dumps(request).encode("utf-8")

        # Content-Length framed protocol (standard MCP stdio transport)
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")

        try:
            # Write request
            self._process.stdin.write(header + body)
            self._process.stdin.flush()

            # Read response header
            content_length = None
            while True:
                line = self._process.stdout.readline().decode("utf-8").rstrip("\r\n")
                if not line:
                    break
                if line.lower().startswith("content-length:"):
                    content_length = int(line.split(":")[1].strip())

            if content_length is None:
                raise ConnectionError("No Content-Length in MCP response")

            # Read response body
            response_body = self._process.stdout.read(content_length)
            response = json.loads(response_body.decode("utf-8"))
            return response

        except (BrokenPipeError, OSError) as e:
            raise ConnectionError(f"OntoMCP process died: {e}") from e

    @staticmethod
    def _find_binary() -> Optional[str]:
        """Find the ontomcp binary in standard locations."""
        for path in DEFAULT_BINARY_PATHS:
            expanded = os.path.expanduser(path)
            if shutil.which(expanded):
                return expanded
        return None
