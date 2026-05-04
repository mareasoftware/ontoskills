"""MCP client that communicates with the ontomcp binary via JSON-RPC 2.0 over stdio.

Uses line-delimited JSON (each message is a single JSON line terminated by \\n).
The ontomcp server auto-detects this wire mode when the first message starts with '{'.

Usage:
    with MCPClient(ontology_root="/path/to/ontologies") as client:
        client.initialize()
        result = client.call_tool("ontoskill", {"q": "create pdf"})
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import select
import subprocess
import threading
from typing import Any

logger = logging.getLogger(__name__)

# Default binary location
DEFAULT_ONTOMCP_BIN = os.path.expanduser("~/.ontoskills/bin/ontomcp")

# Fallback: build artifact inside the repo
_REPO_BIN_CANDIDATES = [
    # Check repo-relative paths
    os.path.join(os.path.dirname(__file__), "..", "..", "mcp", "target", "release", "ontomcp"),
    os.path.join(os.path.dirname(__file__), "..", "..", "mcp", "target", "debug", "ontomcp"),
]


def _resolve_binary(ontomcp_bin: str | None) -> str:
    """Resolve the ontomcp binary path.

    If *ontomcp_bin* is provided and exists, use it directly.
    Otherwise fall back to the default install path, then to build artifacts.
    """
    if ontomcp_bin:
        expanded = os.path.expanduser(ontomcp_bin)
        if os.path.isfile(expanded):
            return expanded
        # The user explicitly gave a path that doesn't exist — let it through
        # so the subprocess error is clear.
        return expanded

    if os.path.isfile(DEFAULT_ONTOMCP_BIN):
        return DEFAULT_ONTOMCP_BIN

    for candidate in _REPO_BIN_CANDIDATES:
        abs_path = os.path.abspath(candidate)
        if os.path.isfile(abs_path):
            return abs_path

    # Last resort — return default and let subprocess tell the user it's missing
    return DEFAULT_ONTOMCP_BIN


class MCPClient:
    """JSON-RPC 2.0 client for the ontomcp MCP server over stdio.

    Parameters
    ----------
    ontomcp_bin:
        Path to the ``ontomcp`` binary.  If ``None``, auto-detected from
        ``~/.ontoskills/bin/ontomcp`` or the repo build directory.
    ontology_root:
        Path passed to ``ontomcp --ontology-root``.  Required.
    """

    def __init__(
        self,
        ontomcp_bin: str | None = None,
        ontology_root: str | None = None,
    ) -> None:
        self._bin = _resolve_binary(ontomcp_bin)
        if not ontology_root:
            raise ValueError(
                "ontology_root is required and must be a non-empty path"
            )
        self._ontology_root = os.path.abspath(ontology_root)
        self._proc: subprocess.Popen | None = None
        self._next_id = 1
        self._lock = threading.Lock()
        self._initialized = False
        # Drain stderr on a background thread so the pipe never blocks.
        self._stderr_thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------
    def __enter__(self) -> "MCPClient":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # noqa: ANN001
        self.close()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Spawn the ontomcp subprocess."""
        if self._proc is not None:
            return

        cmd = [self._bin, "--ontology-root", self._ontology_root]
        logger.info("Starting ontomcp: %s", " ".join(cmd))

        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,  # unbuffered — we manage framing ourselves
        )

        # Register atexit as a backup in case the caller forgets to close().
        atexit.register(self.close)

        # Drain stderr on a daemon thread so the pipe never fills up.
        self._stderr_thread = threading.Thread(
            target=self._drain_stderr, daemon=True, name="ontomcp-stderr"
        )
        self._stderr_thread.start()

    def close(self) -> None:
        """Terminate the subprocess and clean up."""
        if self._proc is None:
            return

        proc = self._proc
        self._proc = None

        # Explicitly close stdin before terminating to flush pending writes.
        if proc.stdin is not None:
            try:
                proc.stdin.close()
            except OSError:
                pass

        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
        except OSError:
            pass  # already dead

        logger.info("ontomcp subprocess stopped (exit code %s)", proc.returncode)

    # ------------------------------------------------------------------
    # JSON-RPC helpers
    # ------------------------------------------------------------------
    def _readline_with_timeout(self, timeout: float = 30.0) -> bytes:
        """Read one line from stdout with a timeout.

        Uses ``select.select`` to avoid blocking indefinitely if the
        server hangs.  Raises ``TimeoutError`` if no data arrives within
        *timeout* seconds.  Linux-only is acceptable for benchmarks.
        """
        assert self._proc is not None and self._proc.stdout is not None
        ready, _, _ = select.select([self._proc.stdout], [], [], timeout)
        if not ready:
            raise TimeoutError(
                f"ontomcp did not respond within {timeout:.0f}s"
            )
        return self._proc.stdout.readline()

    def _send_request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a JSON-RPC request and return the parsed response dict.

        Raises ``RuntimeError`` on JSON-RPC errors or transport failures.
        Raises ``TimeoutError`` if the server does not respond in time.
        """
        if self._proc is None or self._proc.stdin is None or self._proc.stdout is None:
            raise RuntimeError("ontomcp subprocess is not running")

        with self._lock:
            msg_id = self._next_id
            self._next_id += 1

            request: dict[str, Any] = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "method": method,
            }
            if params is not None:
                request["params"] = params

            line = json.dumps(request, separators=(",", ":")) + "\n"
            self._proc.stdin.write(line.encode("utf-8"))
            self._proc.stdin.flush()

            # Read one line back with a timeout.
            raw = self._readline_with_timeout(timeout=30.0)
            if not raw:
                raise RuntimeError(
                    "ontomcp closed stdout unexpectedly (process may have crashed)"
                )

            response = json.loads(raw)

        # Validate response ID matches request ID.
        if response.get("id") != msg_id:
            raise RuntimeError(
                f"JSON-RPC response ID mismatch: expected {msg_id}, "
                f"got {response.get('id')}"
            )

        # Check for JSON-RPC error.
        if "error" in response:
            err = response["error"]
            raise RuntimeError(
                f"JSON-RPC error {err.get('code')}: {err.get('message')}"
            )

        return response

    def _send_notification(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> None:
        """Send a JSON-RPC notification (no id, no response expected)."""
        if self._proc is None or self._proc.stdin is None:
            raise RuntimeError("ontomcp subprocess is not running")

        notification: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params is not None:
            notification["params"] = params

        line = json.dumps(notification, separators=(",", ":")) + "\n"
        with self._lock:
            self._proc.stdin.write(line.encode("utf-8"))
            self._proc.stdin.flush()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def initialize(self) -> dict[str, Any]:
        """Send the MCP ``initialize`` handshake.

        Returns the server's capabilities dict.
        """
        response = self._send_request(
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {
                    "name": "ontoskills-benchmark",
                    "version": "0.1.0",
                },
            },
        )

        # Send the required initialized notification.
        self._send_notification("notifications/initialized")
        self._initialized = True

        return response.get("result", {})

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call an MCP tool via ``tools/call``.

        Parameters
        ----------
        name:
            Tool name (e.g. ``"ontoskill"``).
        arguments:
            Tool arguments dict.

        Returns
        -------
        The parsed ``result`` dict from the server.
        """
        params: dict[str, Any] = {"name": name}
        if arguments is not None:
            params["arguments"] = arguments

        response = self._send_request("tools/call", params)
        return response.get("result", {})

    def list_tools(self) -> list[dict[str, Any]]:
        """List available MCP tools via ``tools/list``."""
        response = self._send_request("tools/list")
        return response.get("result", {}).get("tools", [])

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _drain_stderr(self) -> None:
        """Read stderr lines and log them as warnings."""
        if self._proc is None or self._proc.stderr is None:
            return
        try:
            for raw_line in self._proc.stderr:
                line = raw_line.decode("utf-8", errors="replace").rstrip()
                if line:
                    logger.warning("[ontomcp stderr] %s", line)
        except ValueError:
            # stderr closed
            pass


# ------------------------------------------------------------------
# Smoke test
# ------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    import time

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    ontology_root = sys.argv[1] if len(sys.argv) > 1 else os.environ.get(
        "ONTOMCP_ONTOLOGY_ROOT",
        os.path.expanduser("~/.ontoskills/ontologies"),
    )

    print(f"Ontology root: {ontology_root}")
    print(f"Binary: {_resolve_binary(None)}")
    print()

    with MCPClient(ontology_root=ontology_root) as client:
        t0 = time.perf_counter()
        info = client.initialize()
        elapsed = time.perf_counter() - t0
        print(f"Initialized in {elapsed:.2f}s")
        print(f"  Server: {info.get('serverInfo')}")
        print(f"  Protocol: {info.get('protocolVersion')}")
        print(f"  Capabilities: {list(info.get('capabilities', {}).keys())}")
        print()

        # List tools
        tools = client.list_tools()
        print(f"Available tools ({len(tools)}):")
        for tool_def in tools:
            print(f"  - {tool_def['name']}: {tool_def['description'][:80]}...")
        print()

        # Quick search test — use the first available tool
        search_name = "ontoskill"
        for t in tools:
            if "search" in t["name"].lower() or t["name"] == "ontoskill":
                search_name = t["name"]
                break

        t0 = time.perf_counter()
        result = client.call_tool(search_name, {"intent": "create_pdf"})
        elapsed = time.perf_counter() - t0
        print(f"{search_name} in {elapsed:.3f}s:")
        # Extract the text content from the MCP response
        content = result.get("content", [])
        for item in content:
            if item.get("type") == "text":
                # Pretty-print the first 500 chars
                text = item.get("text", "")
                print(f"  {text[:500]}")
                if len(text) > 500:
                    print(f"  ... ({len(text)} chars total)")
        print()
        print("Smoke test passed.")
