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


def build_section_tree_from_blocks(blocks: list[FlatBlock]) -> list[Section]:
    """Build hierarchical section tree from flat blocks.

    Walks blocks sequentially. Heading blocks create sections;
    non-heading blocks accumulate into the current section's content.
    Stack-based nesting matches heading levels (same algorithm as v1).
    """
    root_sections: list[Section] = []
    stack: list[tuple[int, Section]] = []
    section_order = 0
    current_section = Section(title="", level=0, order=0)
    content_counter = 0

    for block in blocks:
        # Skip child blocks — they're already attached to BulletItem/ProcedureStep.children
        if block.parent_block_id:
            continue
        if block.block_type == "heading":
            # Place current section in tree (preamble or previous heading)
            _place_section(current_section, stack, root_sections)

            section_order += 1
            new_section = Section(
                title=block.content.text,
                level=block.content.level,
                order=section_order,
            )
            current_section = new_section
            content_counter = 0

            # Update stack: pop until parent has lower level
            while stack and stack[-1][0] >= block.content.level:
                stack.pop()
            stack.append((block.content.level, new_section))
        else:
            content_counter += 1
            content_block = block.content
            content_block.content_order = content_counter
            current_section.content.append(content_block)

    # Place final section
    _place_section(current_section, stack, root_sections)

    return root_sections


def _place_section(section, stack, root_sections):
    """Place a section in the tree as subsection of stack parent or as root."""
    if section.level == 0:
        # Preamble — only add as root if it has content
        if section.content:
            root_sections.append(section)
        return
    # Find parent: first stack entry with lower level
    for si in range(len(stack) - 1, -1, -1):
        if stack[si][0] < section.level:
            stack[si][1].subsections.append(section)
            return
    root_sections.append(section)


def _derive_flat_lists(sections: list[Section]):
    """Walk section tree and derive typed flat lists."""
    code_blocks: list[CodeBlock] = []
    tables: list[MarkdownTable] = []
    flowcharts: list[FlowchartBlock] = []
    procedures: list[OrderedProcedure] = []
    templates: list[TemplateBlock] = []

    def _walk(section):
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
            _walk(sub)

    for s in sections:
        _walk(s)

    return code_blocks, tables, flowcharts, procedures, templates


def extract_structural_content(markdown: str) -> ContentExtraction:
    """Parse markdown into a section tree with typed content blocks."""
    blocks = extract_flat_blocks(markdown)
    sections = build_section_tree_from_blocks(blocks)
    code_blocks, tables, flowcharts, procedures, templates = _derive_flat_lists(sections)
    return ContentExtraction(
        sections=sections,
        code_blocks=code_blocks,
        tables=tables,
        flowcharts=flowcharts,
        procedures=procedures,
        templates=templates,
    )


def _extract_ordered_items(ol_open_token, tokens, start_idx, md_lines, block_counter):
    """Extract ordered list items, including nested content blocks inside items.

    Returns (OrderedProcedure, list[FlatBlock]) where the FlatBlocks are child
    blocks with parent_block_id set.
    """
    items = []
    current_position = 0
    depth = 0
    in_item = False
    captured_inline = False

    for j in range(start_idx, len(tokens)):
        t = tokens[j]
        if t.type in ("ordered_list_close", "bullet_list_close"):
            depth -= 1
            if depth == 0:
                break
        elif t.type in ("ordered_list_open", "bullet_list_open"):
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

    if not items:
        return None, []

    # Walk to extract child blocks per item
    child_blocks = []
    item_idx = 0
    j = start_idx + 1
    depth = 1
    while j < len(tokens):
        t = tokens[j]
        if t.type in ("ordered_list_close", "bullet_list_close"):
            depth -= 1
            if depth == 0:
                break
        elif t.type in ("ordered_list_open", "bullet_list_open"):
            depth += 1
        elif t.type == "list_item_open" and depth == 1:
            parent_id = f"blk_{block_counter}_item_{item_idx}"
            k = j + 1
            item_depth = 1
            first_para_skipped = False
            child_order = 0
            while k < len(tokens):
                tk = tokens[k]
                if tk.type == "list_item_close":
                    item_depth -= 1
                    if item_depth == 0:
                        break
                elif tk.type == "list_item_open":
                    item_depth += 1
                elif item_depth == 1 and tk.type == "inline":
                    pass  # skip inline text (already captured)
                elif item_depth >= 1 and tk.type == "paragraph_open" and not first_para_skipped:
                    first_para_skipped = True  # skip first paragraph (item text)
                elif item_depth >= 1 and tk.map:
                    result = _try_extract_child_block(tk, tokens, k, md_lines, block_counter + 1 + len(child_blocks), parent_id, child_order)
                    if result:
                        child_blocks.extend(result)
                        if item_idx < len(items):
                            for r in result:
                                if r.parent_block_id == parent_id:
                                    r.content.content_order = child_order
                                    items[item_idx].children.append(r.content)
                                    child_order += 1
                        k = _skip_extracted_block(tk, tokens, k)
                        continue
                k += 1
            item_idx += 1
        j += 1

    return OrderedProcedure(items=items, content_order=0), child_blocks


def _extract_bullet_items(bl_open_token, tokens, start_idx, md_lines, block_counter):
    """Extract bullet list items, including nested content blocks inside items.

    Returns (BulletListBlock, list[FlatBlock]) where the FlatBlocks are child
    blocks with parent_block_id set. Children are also attached to BulletItem.children.
    """
    items = []
    current_order = 0
    in_item = False
    captured_inline = False
    depth = 0

    for j in range(start_idx, len(tokens)):
        t = tokens[j]
        if t.type in ("bullet_list_close", "ordered_list_close"):
            depth -= 1
            if depth == 0:
                break
        elif t.type in ("bullet_list_open", "ordered_list_open"):
            depth += 1
        elif t.type == "list_item_open" and depth == 1:
            current_order += 1
            in_item = True
            captured_inline = False
        elif t.type == "list_item_close" and depth == 1:
            in_item = False
        elif t.type == "inline" and in_item and not captured_inline and depth == 1:
            items.append(BulletItem(text=t.content, order=current_order))
            captured_inline = True

    if not items:
        return None, []

    # Walk items to find nested blocks
    child_blocks = []
    item_idx = 0
    j = start_idx + 1
    depth = 1
    while j < len(tokens):
        t = tokens[j]
        if t.type in ("bullet_list_close", "ordered_list_close"):
            depth -= 1
            if depth == 0:
                break
        elif t.type in ("bullet_list_open", "ordered_list_open"):
            depth += 1
        elif t.type == "list_item_open" and depth == 1:
            parent_id = f"blk_{block_counter}_item_{item_idx}"
            k = j + 1
            item_depth = 1
            first_para_skipped = False
            child_order = 0
            while k < len(tokens):
                tk = tokens[k]
                if tk.type == "list_item_close":
                    item_depth -= 1
                    if item_depth == 0:
                        break
                elif tk.type == "list_item_open":
                    item_depth += 1
                elif item_depth == 1 and tk.type == "inline":
                    pass
                elif item_depth >= 1 and tk.type == "paragraph_open" and not first_para_skipped:
                    first_para_skipped = True  # skip first paragraph (item text)
                elif item_depth >= 1 and tk.map:
                    result = _try_extract_child_block(tk, tokens, k, md_lines, block_counter + 1 + len(child_blocks), parent_id, child_order)
                    if result:
                        child_blocks.extend(result)
                        if item_idx < len(items):
                            for r in result:
                                if r.parent_block_id == parent_id:
                                    r.content.content_order = child_order
                                    items[item_idx].children.append(r.content)
                                    child_order += 1
                        k = _skip_extracted_block(tk, tokens, k)
                        continue
                k += 1
            item_idx += 1
        j += 1
    return BulletListBlock(items=items, content_order=0), child_blocks


def _skip_extracted_block(token, tokens, idx):
    """After extracting a block at idx, skip past its closing token.

    For structures with open/close pairs (bullet_list, blockquote, table),
    advance idx to the matching close. For single-token blocks (fence,
    paragraph, html_block), return idx + 1.
    """
    close_type = {
        "bullet_list_open": "bullet_list_close",
        "ordered_list_open": "ordered_list_close",
        "blockquote_open": "blockquote_close",
        "table_open": "table_close",
        "paragraph_open": "paragraph_close",
    }.get(token.type)
    if close_type:
        depth = 0
        k = idx
        while k < len(tokens):
            if tokens[k].type == token.type:
                depth += 1
            elif tokens[k].type == close_type:
                depth -= 1
                if depth == 0:
                    return k
            k += 1
    return idx + 1


def _try_extract_child_block(token, tokens, idx, md_lines, block_counter, parent_id, child_order=0):
    """Try to extract child blocks from a token inside a list item.

    Returns a list of FlatBlocks (may be empty, or contain the block plus
    any descendant blocks from nested structures).
    """
    if token.type == "fence" and token.map:
        block = _classify_fence(token, child_order)
        if block:
            return [FlatBlock(
                block_id=f"blk_{block_counter}",
                block_type=block.block_type,
                content=block,
                line_start=token.map[0] + 1,
                line_end=token.map[1],
                parent_block_id=parent_id,
            )]
    elif token.type == "paragraph_open" and token.map:
        para = _extract_paragraph(token, tokens, idx, md_lines, child_order)
        if para:
            return [FlatBlock(
                block_id=f"blk_{block_counter}",
                block_type="paragraph",
                content=para,
                line_start=token.map[0] + 1,
                line_end=token.map[1],
                parent_block_id=parent_id,
            )]
    elif token.type == "bullet_list_open" and token.map:
        bl, nested_children = _extract_bullet_items(token, tokens, idx, md_lines, block_counter)
        if bl:
            result = [FlatBlock(
                block_id=f"blk_{block_counter}",
                block_type="bullet_list",
                content=bl,
                line_start=token.map[0] + 1,
                line_end=token.map[1],
                parent_block_id=parent_id,
            )]
            result.extend(nested_children)
            return result
    elif token.type == "blockquote_open" and token.map:
        bq = _extract_blockquote(token, tokens, idx, md_lines, 0)
        if bq:
            return [FlatBlock(
                block_id=f"blk_{block_counter}",
                block_type="blockquote",
                content=bq,
                line_start=token.map[0] + 1,
                line_end=token.map[1],
                parent_block_id=parent_id,
            )]
    elif token.type == "html_block" and token.map:
        start, end = token.map
        raw = "".join(md_lines[start:end])
        return [FlatBlock(
            block_id=f"blk_{block_counter}",
            block_type="html_block",
            content=HTMLBlock(content=raw.strip(), content_order=child_order),
            line_start=start + 1,
            line_end=end,
            parent_block_id=parent_id,
        )]
    return []


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

        # Ordered list (procedure) — use with_children variant for nested extraction
        if token.type == "ordered_list_open" and token.map:
            proc, child_blocks = _extract_ordered_items(
                token, tokens, i, md_lines, block_counter
            )
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
                blocks.extend(child_blocks)
                block_counter += len(child_blocks)
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

        # Bullet list — use with_children variant for nested extraction
        if token.type == "bullet_list_open" and token.map:
            bl, child_blocks = _extract_bullet_items(
                token, tokens, i, md_lines, block_counter
            )
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
                blocks.extend(child_blocks)
                block_counter += len(child_blocks)
            skip_depth = 0
            while i < len(tokens):
                if tokens[i].type == "bullet_list_open":
                    skip_depth += 1
                elif tokens[i].type == "bullet_list_close":
                    skip_depth -= 1
                    if skip_depth == 0:
                        break
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


def _extract_paragraph(token, _tokens, start_idx, md_lines, content_order):
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
