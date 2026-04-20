"""DocGraph v2 coverage benchmark — line-level metric against 30 real skills."""
import pytest
from pathlib import Path
from compiler.content_parser import extract_flat_blocks

SUP_DIR = Path("/home/marcello/.claude/plugins/cache/claude-plugins-official/superpowers/5.0.7/skills")
ANT_DIR = Path("/home/marcello/.claude/plugins/cache/anthropic-agent-skills/document-skills/3d5951151859/skills")


def _dirs_available():
    return SUP_DIR.is_dir() and ANT_DIR.is_dir()


def _collect_skill_paths():
    paths = []
    for d in sorted(SUP_DIR.iterdir()):
        p = d / "SKILL.md"
        if p.exists():
            paths.append(("sup", p))
    for d in sorted(ANT_DIR.iterdir()):
        p = d / "SKILL.md"
        if p.exists():
            paths.append(("ant", p))
    return paths


def _calc_line_coverage(md, blocks):
    """Calculate line-level coverage.

    A line is 'covered' if it falls within any FlatBlock's line_start..line_end range.
    Blank lines and horizontal rules (---/***/___) are excluded from the denominator.
    """
    lines = md.splitlines()
    covered = set()
    for b in blocks:
        for line_no in range(b.line_start - 1, b.line_end):
            if 0 <= line_no < len(lines):
                covered.add(line_no)
    total_content = sum(1 for i, l in enumerate(lines) if l.strip() and l.strip() not in ("---", "***", "___"))
    covered_content = sum(1 for i in covered if i < len(lines) and lines[i].strip() and lines[i].strip() not in ("---", "***", "___"))
    return covered_content / total_content * 100 if total_content else 100.0


@pytest.mark.benchmark
@pytest.mark.skipif(not _dirs_available(), reason="Skill benchmark directories not available")
def test_coverage_all_skills():
    """Benchmark: measure line-level coverage across all available skills."""
    paths = _collect_skill_paths()
    assert len(paths) >= 20, f"Expected >=20 skills, found {len(paths)}"

    results = []
    for source, path in paths:
        md = path.read_text()
        blocks = extract_flat_blocks(md)
        coverage = _calc_line_coverage(md, blocks)
        results.append((source, path.parent.name, coverage))

    # Report
    avg = sum(c for _, _, c in results) / len(results)
    below_90 = [(s, n, c) for s, n, c in results if c < 90.0]

    # Print report for visibility
    print(f"\n{'='*70}")
    print(f"DOCGRAPH V2 COVERAGE — {len(results)} skills")
    print(f"{'='*70}")
    for s, n, c in sorted(results, key=lambda x: x[2]):
        marker = " <<<" if c < 90 else ""
        print(f"  {s:>3} {n:<38} {c:>6.1f}%{marker}")
    print(f"\n  Average: {avg:.1f}%")
    if below_90:
        print(f"  Below 90%: {len(below_90)} skills")
    print(f"{'='*70}")

    # Assert overall average >= 85% (realistic target for flat extraction without LLM hydration)
    assert avg >= 85.0, f"Average coverage {avg:.1f}% below 85% target"

    # Hard assert: no skill below 60%
    for source, name, cov in results:
        assert cov >= 60.0, f"{source}:{name} coverage {cov:.1f}% below 60%"


@pytest.mark.benchmark
@pytest.mark.skipif(not _dirs_available(), reason="Skill benchmark directories not available")
def test_flat_extraction_preserves_all_block_types():
    """Verify all expected block types are represented in at least one skill."""
    all_types = set()
    for _, path in _collect_skill_paths():
        md = path.read_text()
        blocks = extract_flat_blocks(md)
        for b in blocks:
            all_types.add(b.block_type)
    expected = {"heading", "paragraph", "code_block", "bullet_list", "blockquote", "table", "ordered_procedure", "frontmatter", "html_block"}
    for t in expected:
        assert t in all_types, f"Block type '{t}' not found in any skill"
