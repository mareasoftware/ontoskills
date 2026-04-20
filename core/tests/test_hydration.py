"""Tests for skeleton building (Phase 1b) and hydration (Phase 1c)."""
import pytest
from compiler.schemas import (
    DocumentSkeleton, FlatBlock, HeadingBlock, Paragraph,
    CodeBlock, Section, HTMLBlock, FrontmatterBlock,
    BulletListBlock, BulletItem, OrderedProcedure, ProcedureStep,
)


class TestSkeletonBuilding:
    def test_build_skeleton_prompt_format(self):
        from compiler.content_parser import extract_flat_blocks
        from compiler.prompts import build_skeleton_prompt
        md = "## Section\n\nParagraph text.\n\n```python\nx=1\n```\n"
        blocks = extract_flat_blocks(md)
        prompt = build_skeleton_prompt(blocks)
        assert "blk_0" in prompt
        assert "heading" in prompt
        assert "paragraph" in prompt
        assert "code_block" in prompt

    def test_skeleton_prompt_max_80_chars_preview(self):
        from compiler.content_parser import extract_flat_blocks
        from compiler.prompts import build_skeleton_prompt
        long_text = "A" * 200
        md = f"## Section\n\n{long_text}\n"
        blocks = extract_flat_blocks(md)
        prompt = build_skeleton_prompt(blocks)
        for line in prompt.split("\n"):
            if "blk_" in line and ":" in line:
                preview = line.split(":", 2)[-1].strip()
                assert len(preview) <= 82  # 80 + quotes


class TestHydration:
    def _make_blocks(self, md):
        from compiler.content_parser import extract_flat_blocks
        return extract_flat_blocks(md)

    def test_hydrate_simple_sections(self):
        from compiler.transformer import hydrate_skeleton
        blocks = self._make_blocks("## Overview\n\nIntro text.\n\n## Details\n\nDetail text.\n")
        index = {b.block_id: b for b in blocks}
        skeleton = DocumentSkeleton(
            sections=[
                {"block_id": blocks[0].block_id, "children": [{"block_id": blocks[1].block_id}]},
                {"block_id": blocks[2].block_id, "children": [{"block_id": blocks[3].block_id}]},
            ],
        )
        sections = hydrate_skeleton(skeleton, index)
        assert len(sections) == 2
        assert sections[0].title == "Overview"
        assert sections[0].level == 2
        assert len(sections[0].content) == 1
        assert sections[0].content[0].block_type == "paragraph"

    def test_hydrate_nested_sections(self):
        from compiler.transformer import hydrate_skeleton
        blocks = self._make_blocks("## Parent\n\nText.\n\n### Child\n\nChild text.\n")
        index = {b.block_id: b for b in blocks}
        parent_id = [b.block_id for b in blocks if b.block_type == "heading" and b.content.level == 2][0]
        child_id = [b.block_id for b in blocks if b.block_type == "heading" and b.content.level == 3][0]
        parent_para = [b.block_id for b in blocks if b.block_type == "paragraph"][0]
        child_para = [b.block_id for b in blocks if b.block_type == "paragraph" and b.content.text_content != "Text."][0]
        skeleton = DocumentSkeleton(
            sections=[{
                "block_id": parent_id,
                "children": [
                    {"block_id": parent_para},
                    {"block_id": child_id, "children": [{"block_id": child_para}]},
                ],
            }],
        )
        sections = hydrate_skeleton(skeleton, index)
        assert len(sections) == 1
        assert len(sections[0].subsections) == 1
        assert sections[0].subsections[0].title == "Child"

    def test_fallback_to_v1_on_empty_skeleton(self):
        from compiler.transformer import hydrate_skeleton
        blocks = self._make_blocks("## Section\n\nText.\n")
        index = {b.block_id: b for b in blocks}
        skeleton = DocumentSkeleton(sections=[])  # Empty skeleton
        sections = hydrate_skeleton(skeleton, index, markdown="## Section\n\nText.\n")
        assert len(sections) == 1  # Falls back to v1 builder
        assert sections[0].title == "Section"

    def test_hydrate_with_html_and_frontmatter(self):
        from compiler.transformer import hydrate_skeleton
        md = "---\nname: test\n---\n\n## Section\n\nText.\n\n<div>HTML</div>\n"
        blocks = self._make_blocks(md)
        index = {b.block_id: b for b in blocks}
        fm_id = [b.block_id for b in blocks if b.block_type == "frontmatter"][0]
        heading_id = [b.block_id for b in blocks if b.block_type == "heading"][0]
        para_id = [b.block_id for b in blocks if b.block_type == "paragraph"][0]
        html_id = [b.block_id for b in blocks if b.block_type == "html_block"][0]
        skeleton = DocumentSkeleton(
            sections=[
                {"block_id": fm_id, "children": []},
                {"block_id": heading_id, "children": [
                    {"block_id": para_id},
                    {"block_id": html_id},
                ]},
            ],
        )
        sections = hydrate_skeleton(skeleton, index)
        assert len(sections) == 2
        assert sections[0].content[0].block_type == "frontmatter"
        assert sections[1].content[1].block_type == "html_block"
