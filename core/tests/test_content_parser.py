"""Tests for the content_parser module — DocGraph tree builder."""
import pytest
from compiler.content_parser import extract_structural_content


class TestSectionTree:
    def test_single_section_with_paragraph(self):
        md = "## Overview\n\nThis is the overview text.\n"
        result = extract_structural_content(md)
        assert len(result.sections) == 1
        assert result.sections[0].title == "Overview"
        assert result.sections[0].level == 2
        assert result.sections[0].order == 1
        assert len(result.sections[0].content) == 1
        assert result.sections[0].content[0].block_type == "paragraph"
        assert "overview text" in result.sections[0].content[0].text_content

    def test_multiple_sections_ordered(self):
        md = "## First\n\nText A\n\n## Second\n\nText B\n\n## Third\n\nText C\n"
        result = extract_structural_content(md)
        assert len(result.sections) == 3
        assert result.sections[0].title == "First"
        assert result.sections[1].title == "Second"
        assert result.sections[2].title == "Third"
        assert result.sections[0].order == 1
        assert result.sections[1].order == 2
        assert result.sections[2].order == 3

    def test_nested_subsections(self):
        md = "## Parent\n\nParent text.\n\n### Child A\n\nChild A text.\n\n### Child B\n\nChild B text.\n"
        result = extract_structural_content(md)
        assert len(result.sections) == 1
        assert result.sections[0].title == "Parent"
        assert len(result.sections[0].subsections) == 2
        assert result.sections[0].subsections[0].title == "Child A"
        assert result.sections[0].subsections[0].level == 3
        assert result.sections[0].subsections[1].title == "Child B"

    def test_content_before_first_heading(self):
        """Content before any heading goes into a preamble section."""
        md = "Preamble text.\n\n## First Section\n\nSection text.\n"
        result = extract_structural_content(md)
        assert len(result.sections) == 2
        assert result.sections[0].title == ""
        assert result.sections[0].level == 0
        assert result.sections[0].order == 0
        assert "Preamble text" in result.sections[0].content[0].text_content
        assert result.sections[1].title == "First Section"


class TestParagraphExtraction:
    def test_paragraph_preserves_inline_formatting(self):
        md = "## Section\n\nThis has **bold** and `inline code`.\n"
        result = extract_structural_content(md)
        para = result.sections[0].content[0]
        assert para.block_type == "paragraph"
        assert "**bold**" in para.text_content
        assert "`inline code`" in para.text_content

    def test_multiple_paragraphs_in_section(self):
        md = "## Section\n\nFirst paragraph.\n\nSecond paragraph.\n\nThird paragraph.\n"
        result = extract_structural_content(md)
        assert len(result.sections[0].content) == 3
        assert result.sections[0].content[0].text_content.strip() == "First paragraph."
        assert result.sections[0].content[2].text_content.strip() == "Third paragraph."

    def test_paragraph_content_order(self):
        md = "## S\n\nPara 1.\n\n- bullet\n\nPara 2.\n"
        result = extract_structural_content(md)
        section = result.sections[0]
        assert section.content[0].content_order == 1
        assert section.content[1].content_order == 2
        assert section.content[2].content_order == 3


class TestBulletListExtraction:
    def test_bullet_list_in_section(self):
        md = "## Section\n\n- First item\n- Second item\n- Third item\n"
        result = extract_structural_content(md)
        bl = result.sections[0].content[0]
        assert bl.block_type == "bullet_list"
        assert len(bl.items) == 3
        assert bl.items[0].text == "First item"
        assert bl.items[0].order == 1
        assert bl.items[2].order == 3

    def test_bullet_list_content_order(self):
        md = "## S\n\nIntro text.\n\n- Item A\n- Item B\n"
        result = extract_structural_content(md)
        section = result.sections[0]
        assert section.content[0].block_type == "paragraph"
        assert section.content[0].content_order == 1
        assert section.content[1].block_type == "bullet_list"
        assert section.content[1].content_order == 2


class TestBlockQuoteExtraction:
    def test_blockquote_in_section(self):
        md = "## Section\n\n> This is a quote.\n"
        result = extract_structural_content(md)
        bq = result.sections[0].content[0]
        assert bq.block_type == "blockquote"
        assert "This is a quote" in bq.content

    def test_blockquote_attribution(self):
        md = "## Section\n\n> Clean code always looks like it was written by someone who cares.\n>\n> — Robert C. Martin\n"
        result = extract_structural_content(md)
        bq = result.sections[0].content[0]
        assert bq.block_type == "blockquote"
        assert "Clean code" in bq.content


class TestExistingBlocksInSection:
    def test_code_block_in_section(self):
        md = "## Example\n\n```python\nprint('hello')\n```\n"
        result = extract_structural_content(md)
        section = result.sections[0]
        assert len(section.content) == 1
        assert section.content[0].block_type == "code_block"
        assert section.content[0].language == "python"

    def test_table_in_section(self):
        md = "## Data\n\n| a | b |\n|---|---|\n| 1 | 2 |\n"
        result = extract_structural_content(md)
        section = result.sections[0]
        assert section.content[0].block_type == "table"
        assert section.content[0].row_count == 1

    def test_flowchart_in_section(self):
        md = "## Flow\n\n```mermaid\ngraph TD\n    A --> B\n```\n"
        result = extract_structural_content(md)
        section = result.sections[0]
        assert section.content[0].block_type == "flowchart"
        assert section.content[0].chart_type == "mermaid"

    def test_template_in_section(self):
        md = "## Template\n\n```text\nHello {name}\n```\n"
        result = extract_structural_content(md)
        section = result.sections[0]
        assert section.content[0].block_type == "template"
        assert "name" in section.content[0].detected_variables

    def test_ordered_procedure_in_section(self):
        md = "## Steps\n\n1. First\n2. Second\n3. Third\n"
        result = extract_structural_content(md)
        section = result.sections[0]
        assert section.content[0].block_type == "ordered_procedure"
        assert len(section.content[0].items) == 3

    def test_mixed_content_in_section(self):
        md = "## Section\n\nIntro paragraph.\n\n- Bullet 1\n- Bullet 2\n\n```python\nx=1\n```\n\nClosing text.\n"
        result = extract_structural_content(md)
        section = result.sections[0]
        assert len(section.content) == 4
        assert section.content[0].block_type == "paragraph"
        assert section.content[1].block_type == "bullet_list"
        assert section.content[2].block_type == "code_block"
        assert section.content[3].block_type == "paragraph"
        assert section.content[0].content_order == 1
        assert section.content[1].content_order == 2
        assert section.content[2].content_order == 3
        assert section.content[3].content_order == 4


class TestBackwardCompatFlatLists:
    def test_flat_code_blocks_populated(self):
        md = "## S\n\n```python\nx=1\n```\n\n```bash\necho hi\n```\n"
        result = extract_structural_content(md)
        assert len(result.code_blocks) == 2

    def test_flat_tables_populated(self):
        md = "## S\n\n| a | b |\n|---|---|\n| 1 | 2 |\n"
        result = extract_structural_content(md)
        assert len(result.tables) == 1

    def test_flat_flowcharts_populated(self):
        md = "## S\n\n```mermaid\ngraph TD\n    A --> B\n```\n"
        result = extract_structural_content(md)
        assert len(result.flowcharts) == 1

    def test_flat_procedures_populated(self):
        md = "## S\n\n1. Step one\n2. Step two\n"
        result = extract_structural_content(md)
        assert len(result.procedures) == 1
        assert len(result.procedures[0].items) == 2

    def test_flat_templates_populated(self):
        md = "## S\n\n```text\nHello {name}\n```\n"
        result = extract_structural_content(md)
        assert len(result.templates) == 1

    def test_empty_markdown(self):
        md = ""
        result = extract_structural_content(md)
        assert result.sections == []
        assert result.code_blocks == []
        assert result.tables == []


class TestGuardrails:
    def test_python_fstring_not_template(self):
        md = '## S\n\n```python\nprint(f"Hello {name}")\n```\n'
        result = extract_structural_content(md)
        assert len(result.templates) == 0
        assert len(result.code_blocks) == 1

    def test_nested_ordered_list_only_top_level(self):
        md = "## S\n\n1. First\n   1. Nested\n   2. Nested 2\n2. Second\n"
        result = extract_structural_content(md)
        proc = result.sections[0].content[0]
        assert proc.block_type == "ordered_procedure"
        assert len(proc.items) == 2


from compiler.content_parser import extract_flat_blocks


class TestFlatExtraction:
    def test_flat_blocks_have_ids(self):
        md = "## Section\n\nParagraph text.\n\n```python\nx=1\n```\n"
        blocks = extract_flat_blocks(md)
        assert all(b.block_id.startswith("blk_") for b in blocks)
        assert len(blocks) >= 3  # heading, paragraph, code_block

    def test_flat_blocks_line_ranges(self):
        md = "## Section\n\nParagraph text.\n"
        blocks = extract_flat_blocks(md)
        for b in blocks:
            assert b.line_start >= 0
            assert b.line_end >= b.line_start

    def test_frontmatter_extracted(self):
        md = "---\nname: test-skill\ndescription: A test\n---\n\n## Section\n\nText.\n"
        blocks = extract_flat_blocks(md)
        fm = [b for b in blocks if b.block_type == "frontmatter"]
        assert len(fm) == 1
        assert fm[0].content.properties["name"] == "test-skill"

    def test_html_block_extracted(self):
        md = "## Section\n\n<HARD-GATE>Do not proceed</HARD-GATE>\n\nText.\n"
        blocks = extract_flat_blocks(md)
        html = [b for b in blocks if b.block_type == "html_block"]
        assert len(html) == 1
        assert "HARD-GATE" in html[0].content.content

    def test_heading_blocks_extracted(self):
        md = "## First\n\nText.\n\n### Second\n\nMore.\n"
        blocks = extract_flat_blocks(md)
        headings = [b for b in blocks if b.block_type == "heading"]
        assert len(headings) == 2
        assert headings[0].content.text == "First"
        assert headings[0].content.level == 2

    def test_flat_extraction_covers_all_types(self):
        md = "---\nname: test\n---\n\n## Title\n\nParagraph.\n\n- Item 1\n- Item 2\n\n> Quote\n\n```python\nx=1\n```\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n1. Step 1\n2. Step 2\n\n<div>HTML</div>\n"
        blocks = extract_flat_blocks(md)
        types = {b.block_type for b in blocks}
        assert "frontmatter" in types
        assert "heading" in types
        assert "paragraph" in types
        assert "bullet_list" in types
        assert "blockquote" in types
        assert "code_block" in types
        assert "table" in types
        assert "ordered_procedure" in types
        assert "html_block" in types
