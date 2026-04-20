"""
Structural Content Parser.

Extracts code blocks, tables, flowcharts, ordered procedures, and templates
from markdown using markdown-it-py for deterministic, lossless parsing.
"""

import re

from compiler.schemas import (
    CodeBlock, ContentExtraction, FlowchartBlock,
    MarkdownTable, OrderedProcedure, ProcedureStep, TemplateBlock,
)


# Languages that are always CodeBlock (never checked for template patterns)
PROGRAMMING_LANGUAGES = frozenset({
    "python", "py", "bash", "sh", "shell", "zsh", "fish",
    "typescript", "ts", "javascript", "js", "jsx", "tsx",
    "go", "rust", "rs", "java", "c", "cpp", "cs", "ruby", "rb",
    "php", "swift", "kotlin", "kt", "scala", "r", "perl",
    "lua", "dart", "elixir", "erlang", "haskell", "hs",
    "sql", "graphql", "yaml", "yml", "json", "xml", "toml",
    "dockerfile", "makefile", "cmake", "nginx", "apache",
})

FLOWCHART_LANGUAGES = frozenset({"dot", "graphviz", "mermaid"})

NEUTRAL_LANGUAGES = frozenset({
    "text", "markdown", "md", "prompt", "jinja", "j2", "jinja2", "template", "",
})

_TEMPLATE_VAR_RE = re.compile(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}')


def extract_structural_content(markdown: str) -> ContentExtraction:
    """Parse markdown and extract structural content blocks.

    Uses markdown-it-py for tokenization. Tables use line-based slicing
    via token.map for raw markdown fidelity. Fenced blocks (code,
    flowcharts, templates) use token.content from the parser for
    clean inner content without fence markers.
    """
    from markdown_it import MarkdownIt
    from mdit_py_plugins.front_matter import front_matter_plugin

    md_it = MarkdownIt("commonmark", {"html": True}).enable("table")
    front_matter_plugin(md_it)
    tokens = md_it.parse(markdown)

    md_lines = markdown.splitlines(keepends=True)

    code_blocks: list[CodeBlock] = []
    tables: list[MarkdownTable] = []
    flowcharts: list[FlowchartBlock] = []
    procedures: list[OrderedProcedure] = []
    templates: list[TemplateBlock] = []

    i = 0
    while i < len(tokens):
        token = tokens[i]

        if token.type == "fence" and token.map:
            block = _classify_fence(token, md_lines)
            if isinstance(block, CodeBlock):
                code_blocks.append(block)
            elif isinstance(block, FlowchartBlock):
                flowcharts.append(block)
            elif isinstance(block, TemplateBlock):
                templates.append(block)

        elif token.type == "table_open" and token.map:
            table = _extract_table(token, tokens, i, md_lines)
            if table:
                tables.append(table)

        elif token.type == "ordered_list_open" and token.map:
            proc = _extract_ordered_procedure(token, tokens, i)
            if proc:
                procedures.append(proc)
            # Skip all tokens until the matching ordered_list_close
            # so nested ordered_list_open tokens are not picked up separately
            depth = 0
            while i < len(tokens):
                if tokens[i].type == "ordered_list_open":
                    depth += 1
                elif tokens[i].type == "ordered_list_close":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1

        i += 1

    return ContentExtraction(
        code_blocks=code_blocks,
        tables=tables,
        flowcharts=flowcharts,
        procedures=procedures,
        templates=templates,
    )


def _slice_lines(md_lines: list[str], start: int, end: int) -> str:
    """Extract lines [start, end) from source, preserving exact formatting."""
    return "".join(md_lines[start:end])


def _classify_fence(token, md_lines: list[str]):
    """Classify a fence token as CodeBlock, FlowchartBlock, or TemplateBlock.

    Uses token.content for the inner content (excludes fence markers),
    and token.map for source line tracking only.
    """
    info = (token.info or "").strip()
    lang = info.split()[0] if info else ""
    lang_lower = lang.lower()
    content = token.content

    if lang_lower in FLOWCHART_LANGUAGES:
        chart_type = "mermaid" if lang_lower == "mermaid" else "graphviz"
        return FlowchartBlock(source=content, chart_type=chart_type)

    if lang_lower in PROGRAMMING_LANGUAGES:
        return CodeBlock(
            language=lang_lower,
            content=content,
            source_line_start=token.map[0] + 1,
            source_line_end=token.map[1],
        )

    # Neutral or unknown language — check for template variables
    if lang_lower in NEUTRAL_LANGUAGES:
        vars_found = _TEMPLATE_VAR_RE.findall(content)
        if vars_found:
            return TemplateBlock(content=content, detected_variables=vars_found)

    return CodeBlock(
        language=lang_lower,
        content=content,
        source_line_start=token.map[0] + 1,
        source_line_end=token.map[1],
    )


def _extract_table(table_open_token, tokens, start_idx, md_lines):
    """Extract a markdown table via map slicing."""
    if not table_open_token.map:
        return None
    start, end = table_open_token.map
    raw_source = _slice_lines(md_lines, start, end)

    # Count data rows (skip header rows — those with th_open children)
    row_count = 0
    for j in range(start_idx, len(tokens)):
        t = tokens[j]
        if t.type == "table_close":
            break
        if t.type == "tr_open":
            # Check if next token is td_open (data) vs th_open (header)
            if j + 1 < len(tokens) and tokens[j + 1].type == "td_open":
                row_count += 1

    # Try to find caption from preceding line
    caption = None
    if start > 0:
        preceding_line = md_lines[start - 1].strip() if start - 1 < len(md_lines) else ""
        if preceding_line and not preceding_line.startswith("|"):
            caption = preceding_line.rstrip(":")

    return MarkdownTable(
        markdown_source=raw_source,
        caption=caption,
        row_count=row_count,
    )


def _extract_ordered_procedure(ol_open_token, tokens, start_idx):
    """Extract ordered list items as an OrderedProcedure.

    Handles nested lists by tracking depth — only top-level items are extracted.
    Handles multiple inline tokens per item by only capturing the first.
    """
    items = []
    current_position = 0
    depth = 0
    in_item = False
    captured_inline = False

    for j in range(start_idx, len(tokens)):
        t = tokens[j]
        if t.type == "ordered_list_close":
            depth -= 1
            if depth == 0:
                break
        elif t.type == "ordered_list_open":
            depth += 1
        elif t.type == "list_item_open":
            if depth == 1:
                current_position += 1
                in_item = True
                captured_inline = False
        elif t.type == "list_item_close":
            if depth == 1:
                in_item = False
        elif t.type == "inline" and in_item and not captured_inline and depth == 1:
            items.append(ProcedureStep(text=t.content, position=current_position))
            captured_inline = True

    if items:
        return OrderedProcedure(items=items)
    return None
