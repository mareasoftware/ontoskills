"""
SPARQL Query Execution Module.

Execute SPARQL queries against the skills ontology
with multiple output formats.
"""

import json
import logging
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from rdflib import Graph

from compiler.exceptions import SPARQLError

logger = logging.getLogger(__name__)


def execute_sparql(ontology_path: Path, query: str) -> list[dict[str, Any]]:
    """
    Execute SPARQL query against ontology.

    Args:
        ontology_path: Path to skills.ttl
        query: SPARQL query string

    Returns:
        List of result bindings as dictionaries

    Raises:
        SPARQLError: If query is invalid or execution fails
    """
    if not ontology_path.exists():
        raise SPARQLError(f"Ontology file not found: {ontology_path}")

    try:
        graph = Graph()
        graph.parse(ontology_path, format="turtle")
        logger.debug(f"Loaded ontology with {len(graph)} triples")
    except Exception as e:
        raise SPARQLError(f"Failed to load ontology: {e}")

    # Validate query doesn't contain mutations
    query_upper = query.upper()
    mutation_keywords = ["INSERT", "DELETE", "DROP", "CREATE", "CLEAR", "LOAD"]
    for keyword in mutation_keywords:
        if keyword in query_upper:
            raise SPARQLError(f"Mutation operations ({keyword}) are not supported")

    try:
        results = graph.query(query)
        logger.info(f"Query returned {len(results)} results")

        # Convert to list of dicts
        rows = []
        for row in results:
            row_dict = {}
            for i, var in enumerate(results.vars):
                val = row[i]
                if val is not None:
                    row_dict[str(var)] = str(val)
                else:
                    row_dict[str(var)] = None
            rows.append(row_dict)

        return rows, list(results.vars) if results.vars else []

    except Exception as e:
        raise SPARQLError(f"Invalid query: {e}")


def format_results(
    results: list[dict[str, Any]],
    format: str,
    vars: list[str]
) -> str:
    """
    Format SPARQL results for output.

    Args:
        results: List of result bindings
        format: Output format (table, json, turtle)
        vars: List of variable names

    Returns:
        Formatted string output
    """
    if format == "json":
        return json.dumps(results, indent=2, default=str)

    elif format == "turtle":
        lines = []
        for row in results:
            for var, val in row.items():
                if val is not None:
                    lines.append(f"{var}: {val}")
            lines.append("")  # Blank line between rows
        return "\n".join(lines)

    else:  # table (default)
        console = Console()
        table = Table(title="Query Results", show_header=True, header_style="bold")

        # Add columns
        for var in vars:
            table.add_column(str(var))

        # Add rows
        for row in results:
            table.add_row(*[row.get(str(v), "") or "" for v in vars])

        # Capture output
        with console.capture() as capture:
            console.print(table)

        return capture.get()
