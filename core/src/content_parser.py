"""
DocGraph Content Parser.

Transforms markdown into a section tree (DocGraph) where every element
is a typed content block within its section context. Uses markdown-it-py
for deterministic, CommonMark-compliant tokenization.

Two-pass approach:
  1. Group tokens by heading boundaries
  2. Build nested section tree via stack-based nesting
"""

import re

from compiler.schemas import (
    BlockQuoteBlock, BulletItem, BulletListBlock,
    CodeBlock, ContentExtraction, FlatBlock, FlowchartBlock,
    FrontmatterBlock, HeadingBlock, HTMLBlock,
    MarkdownTable, OrderedProcedure, Paragraph, ProcedureStep,
    Section, TemplateBlock,
)


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
    """Parse markdown into a section tree with typed content blocks."""
    from markdown_it import MarkdownIt
    from mdit_py_plugins.front_matter import front_matter_plugin

    md_it = MarkdownIt("commonmark", {"html": True}).enable("table")
    front_matter_plugin(md_it)
    tokens = md_it.parse(markdown)
    md_lines = markdown.splitlines(keepends=True)

    # Pass 1: Group tokens by heading boundaries
    groups = _group_by_headings(tokens)

    # Pass 2: Build tree and extract content
    sections = _build_section_tree(groups, tokens, md_lines)

    # Derive flat lists from tree for backward compatibility
    code_blocks, tables, flowcharts, procedures, templates = [], [], [], [], []
    for section in sections:
        _collect_flat_lists(section, code_blocks, tables, flowcharts, procedures, templates)

    return ContentExtraction(
        sections=sections,
        code_blocks=code_blocks,
        tables=tables,
        flowcharts=flowcharts,
        procedures=procedures,
        templates=templates,
    )


def extract_flat_blocks(markdown: str) -> list[FlatBlock]:
    """Extract ALL content blocks as a flat list with unique block_ids.

    Phase 1a of Skeleton & Hydration architecture. Every markdown element
    becomes a FlatBlock with block_id, line range, and byte-perfect content.
    """
    from markdown_it import MarkdownIt
    from mdit_py_plugins.front_matter import front_matter_plugin

    md_it = MarkdownIt("commonmark", {"html": True}).enable("table")
    front_matter_plugin(md_it)
    tokens = md_it.parse(markdown)
    md_lines = markdown.splitlines(keepends=True)

    blocks: list[FlatBlock] = []
    block_counter = 0
    i = 0

    while i < len(tokens):
        token = tokens[i]

        # Frontmatter
        if token.type == "front_matter" and token.map:
            start, end = token.map
            raw = "".join(md_lines[start:end])
            props: dict[str, str] = {}
            for line in raw.split("\n"):
                if ":" in line and not line.strip().startswith("---"):
                    key, _, val = line.partition(":")
                    key = key.strip()
                    val = val.strip()
                    if key and val:
                        props[key] = val
            bid = f"blk_{block_counter}"
            block_counter += 1
            blocks.append(FlatBlock(
                block_id=bid,
                block_type="frontmatter",
                content=FrontmatterBlock(raw_yaml=raw, properties=props, content_order=0),
                line_start=start + 1,
                line_end=end,
            ))
            i += 1
            continue

        # HTML block
        if token.type == "html_block" and token.map:
            start, end = token.map
            raw = "".join(md_lines[start:end])
            bid = f"blk_{block_counter}"
            block_counter += 1
            blocks.append(FlatBlock(
                block_id=bid,
                block_type="html_block",
                content=HTMLBlock(content=raw.strip(), content_order=0),
                line_start=start + 1,
                line_end=end,
            ))
            i += 1
            continue

        # Heading
        if token.type == "heading_open" and token.map:
            level = int(token.tag[1])
            title = ""
            if i + 1 < len(tokens) and tokens[i + 1].type == "inline":
                title = tokens[i + 1].content
            start = token.map[0]
            end = token.map[1]
            bid = f"blk_{block_counter}"
            block_counter += 1
            blocks.append(FlatBlock(
                block_id=bid,
                block_type="heading",
                content=HeadingBlock(text=title, level=level, content_order=0),
                line_start=start + 1,
                line_end=end,
            ))
            i += 3  # heading_open, inline, heading_close
            continue

        # Fence (code/flowchart/template)
        if token.type == "fence" and token.map:
            block = _classify_fence(token, 0)
            if block is not None:
                bid = f"blk_{block_counter}"
                block_counter += 1
                blocks.append(FlatBlock(
                    block_id=bid,
                    block_type=block.block_type,
                    content=block,
                    line_start=token.map[0] + 1,
                    line_end=token.map[1],
                ))
            i += 1
            continue

        # Table
        if token.type == "table_open" and token.map:
            table = _extract_table(token, tokens, i, md_lines, 0)
            if table:
                bid = f"blk_{block_counter}"
                block_counter += 1
                blocks.append(FlatBlock(
                    block_id=bid,
                    block_type="table",
                    content=table,
                    line_start=token.map[0] + 1,
                    line_end=token.map[1],
                ))
            while i < len(tokens) and tokens[i].type != "table_close":
                i += 1
            i += 1
            continue

        # Ordered list (procedure)
        if token.type == "ordered_list_open" and token.map:
            proc = _extract_ordered_procedure(token, tokens, i, 0)
            if proc:
                bid = f"blk_{block_counter}"
                block_counter += 1
                blocks.append(FlatBlock(
                    block_id=bid,
                    block_type="ordered_procedure",
                    content=proc,
                    line_start=token.map[0] + 1,
                    line_end=token.map[1],
                ))
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
            continue

        # Bullet list
        if token.type == "bullet_list_open" and token.map:
            bl = _extract_bullet_list(token, tokens, i, 0)
            if bl:
                bid = f"blk_{block_counter}"
                block_counter += 1
                blocks.append(FlatBlock(
                    block_id=bid,
                    block_type="bullet_list",
                    content=bl,
                    line_start=token.map[0] + 1,
                    line_end=token.map[1],
                ))
            while i < len(tokens) and tokens[i].type != "bullet_list_close":
                i += 1
            i += 1
            continue

        # Blockquote
        if token.type == "blockquote_open" and token.map:
            bq = _extract_blockquote(token, tokens, i, md_lines, 0)
            if bq:
                bid = f"blk_{block_counter}"
                block_counter += 1
                blocks.append(FlatBlock(
                    block_id=bid,
                    block_type="blockquote",
                    content=bq,
                    line_start=token.map[0] + 1,
                    line_end=token.map[1],
                ))
            while i < len(tokens) and tokens[i].type != "blockquote_close":
                i += 1
            i += 1
            continue

        # Paragraph (or HTML-dominant paragraph promoted to html_block)
        if token.type == "paragraph_open" and token.map:
            # Check if paragraph contains html_inline children (e.g. <HARD-GATE>)
            inline_token = tokens[i + 1] if i + 1 < len(tokens) and tokens[i + 1].type == "inline" else None
            is_html_dominant = False
            if inline_token and inline_token.children:
                html_chars = sum(len(c.content) for c in inline_token.children if c.type == "html_inline")
                text_chars = sum(len(c.content) for c in inline_token.children if c.type == "text" and c.content.strip())
                is_html_dominant = html_chars > 0 and html_chars >= text_chars

            if is_html_dominant:
                start, end = token.map
                raw = "".join(md_lines[start:end]).strip()
                bid = f"blk_{block_counter}"
                block_counter += 1
                blocks.append(FlatBlock(
                    block_id=bid,
                    block_type="html_block",
                    content=HTMLBlock(content=raw, content_order=0),
                    line_start=start + 1,
                    line_end=end,
                ))
            else:
                para = _extract_paragraph(token, tokens, i, md_lines, 0)
                if para:
                    bid = f"blk_{block_counter}"
                    block_counter += 1
                    blocks.append(FlatBlock(
                        block_id=bid,
                        block_type="paragraph",
                        content=para,
                        line_start=token.map[0] + 1,
                        line_end=token.map[1],
                    ))
            i += 1
            continue

        i += 1

    return blocks


def _collect_flat_lists(section, code_blocks, tables, flowcharts, procedures, templates):
    """Walk section tree and collect flat lists for backward compatibility."""
    for block in section.content:
        if block.block_type == "code_block":
            code_blocks.append(block)
        elif block.block_type == "table":
            tables.append(block)
        elif block.block_type == "flowchart":
            flowcharts.append(block)
        elif block.block_type == "ordered_procedure":
            procedures.append(block)
        elif block.block_type == "template":
            templates.append(block)
    for sub in section.subsections:
        _collect_flat_lists(sub, code_blocks, tables, flowcharts, procedures, templates)


def _group_by_headings(tokens):
    """Group tokens into buckets delimited by heading_open/heading_close pairs.

    Returns list of (level, title, token_start, token_end) tuples.
    Content before the first heading gets level=0, title="".
    """
    groups = []
    current_level = 0
    current_title = ""
    current_start = 0
    in_heading = False

    for i, token in enumerate(tokens):
        if token.type == "heading_open":
            # Close previous group
            if i > current_start:
                groups.append((current_level, current_title, current_start, i))
            current_start = i
            current_level = int(token.tag[1])  # h1 -> 1, h2 -> 2
            in_heading = True
        elif token.type == "inline" and in_heading:
            current_title = token.content
        elif token.type == "heading_close":
            in_heading = False

    # Final group
    if current_start < len(tokens):
        groups.append((current_level, current_title, current_start, len(tokens)))

    return groups


def _build_section_tree(groups, tokens, md_lines):
    """Convert heading groups into nested Section tree using stack-based nesting."""
    root_sections = []
    section_order = 0
    stack = []  # (level, Section)

    for group_level, group_title, tok_start, tok_end in groups:
        if group_level == 0:
            section_order = 0
        else:
            section_order += 1

        section_tokens = tokens[tok_start:tok_end]
        content = _extract_section_content(section_tokens, md_lines)

        section = Section(
            title=group_title,
            level=group_level,
            order=section_order,
            content=content,
        )

        # Place in tree: pop until parent has lower level
        while stack and stack[-1][0] >= group_level:
            stack.pop()

        if stack:
            stack[-1][1].subsections.append(section)
        else:
            root_sections.append(section)

        if group_level > 0:
            stack.append((group_level, section))

    return root_sections


def _extract_section_content(section_tokens, md_lines):
    """Extract ordered content blocks from a section's token range."""
    content = []
    order = 0
    i = 0

    while i < len(section_tokens):
        token = section_tokens[i]

        if token.type == "heading_open":
            # Skip heading tokens (they define the section, not content)
            i += 3  # heading_open, inline, heading_close
            continue

        if token.type == "fence" and token.map:
            order += 1
            block = _classify_fence(token, order)
            if block is not None:
                content.append(block)
            else:
                order -= 1
            i += 1
            continue

        if token.type == "table_open" and token.map:
            order += 1
            table = _extract_table(token, section_tokens, i, md_lines, order)
            if table:
                content.append(table)
            else:
                order -= 1
            # Skip to table_close
            while i < len(section_tokens) and section_tokens[i].type != "table_close":
                i += 1
            i += 1
            continue

        if token.type == "ordered_list_open" and token.map:
            order += 1
            proc = _extract_ordered_procedure(token, section_tokens, i, order)
            if proc:
                content.append(proc)
            else:
                order -= 1
            # Skip to ordered_list_close
            depth = 0
            while i < len(section_tokens):
                if section_tokens[i].type == "ordered_list_open":
                    depth += 1
                elif section_tokens[i].type == "ordered_list_close":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            i += 1
            continue

        if token.type == "bullet_list_open" and token.map:
            order += 1
            bl = _extract_bullet_list(token, section_tokens, i, order)
            if bl:
                content.append(bl)
            else:
                order -= 1
            # Skip to bullet_list_close
            while i < len(section_tokens) and section_tokens[i].type != "bullet_list_close":
                i += 1
            i += 1
            continue

        if token.type == "blockquote_open" and token.map:
            order += 1
            bq = _extract_blockquote(token, section_tokens, i, md_lines, order)
            if bq:
                content.append(bq)
            else:
                order -= 1
            # Skip to blockquote_close
            while i < len(section_tokens) and section_tokens[i].type != "blockquote_close":
                i += 1
            i += 1
            continue

        if token.type == "paragraph_open" and token.map:
            order += 1
            para = _extract_paragraph(token, section_tokens, i, md_lines, order)
            if para:
                content.append(para)
            else:
                order -= 1
            i += 1
            continue

        i += 1

    return content


def _classify_fence(token, content_order):
    """Classify a fence token. Returns typed block with block_type set."""
    info = (token.info or "").strip()
    lang = info.split()[0] if info else ""
    lang_lower = lang.lower()
    content = token.content

    if lang_lower in FLOWCHART_LANGUAGES:
        chart_type = "mermaid" if lang_lower == "mermaid" else "graphviz"
        return FlowchartBlock(source=content, chart_type=chart_type, content_order=content_order)

    if lang_lower in PROGRAMMING_LANGUAGES:
        return CodeBlock(
            language=lang_lower,
            content=content,
            source_line_start=token.map[0] + 1,
            source_line_end=token.map[1],
            content_order=content_order,
        )

    if lang_lower in NEUTRAL_LANGUAGES:
        vars_found = list(dict.fromkeys(_TEMPLATE_VAR_RE.findall(content)))
        if vars_found:
            return TemplateBlock(content=content, detected_variables=vars_found, content_order=content_order)

    return CodeBlock(
        language=lang_lower,
        content=content,
        source_line_start=token.map[0] + 1,
        source_line_end=token.map[1],
        content_order=content_order,
    )


def _extract_paragraph(token, section_tokens, start_idx, md_lines, content_order):
    """Extract paragraph text via map slicing."""
    if not token.map:
        return None
    start, end = token.map
    text = "".join(md_lines[start:end]).strip()
    if not text:
        return None
    return Paragraph(text_content=text, content_order=content_order)


def _extract_table(table_open_token, tokens, start_idx, md_lines, content_order):
    """Extract a markdown table via map slicing."""
    if not table_open_token.map:
        return None
    start, end = table_open_token.map
    raw_source = "".join(md_lines[start:end])

    row_count = 0
    for j in range(start_idx, len(tokens)):
        t = tokens[j]
        if t.type == "table_close":
            break
        if t.type == "tr_open":
            if j + 1 < len(tokens) and tokens[j + 1].type == "td_open":
                row_count += 1

    caption = None
    for k in range(start - 1, -1, -1):
        preceding_line = md_lines[k].strip()
        if not preceding_line:
            continue
        if preceding_line.startswith("|"):
            break
        caption = preceding_line.rstrip(":")
        break

    return MarkdownTable(
        markdown_source=raw_source,
        caption=caption,
        row_count=row_count,
        content_order=content_order,
    )


def _extract_ordered_procedure(ol_open_token, tokens, start_idx, content_order):
    """Extract ordered list items as an OrderedProcedure."""
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
        return OrderedProcedure(items=items, content_order=content_order)
    return None


def _extract_bullet_list(bl_open_token, tokens, start_idx, content_order):
    """Extract bullet list items."""
    items = []
    current_order = 0
    in_item = False
    captured_inline = False

    for j in range(start_idx, len(tokens)):
        t = tokens[j]
        if t.type == "bullet_list_close":
            break
        if t.type == "list_item_open":
            current_order += 1
            in_item = True
            captured_inline = False
        elif t.type == "list_item_close":
            in_item = False
        elif t.type == "inline" and in_item and not captured_inline:
            items.append(BulletItem(text=t.content, order=current_order))
            captured_inline = True

    if items:
        return BulletListBlock(items=items, content_order=content_order)
    return None


def _extract_blockquote(bq_open_token, tokens, start_idx, md_lines, content_order):
    """Extract blockquote content via map slicing."""
    if not bq_open_token.map:
        return None
    start, end = bq_open_token.map
    raw = "".join(md_lines[start:end])
    # Strip leading "> " from each line
    lines = raw.split("\n")
    clean_lines = []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("> "):
            clean_lines.append(stripped[2:])
        elif stripped == ">":
            clean_lines.append("")
        else:
            clean_lines.append(stripped)
    content = "\n".join(clean_lines).strip()
    if not content:
        return None

    # Try to detect attribution (last line starting with "—")
    attribution = None
    if clean_lines and clean_lines[-1].strip().startswith("\u2014"):
        attribution = clean_lines[-1].strip().lstrip("\u2014").strip()
        content = "\n".join(clean_lines[:-1]).strip()

    return BlockQuoteBlock(content=content, attribution=attribution, content_order=content_order)
