import pytest
from pathlib import Path
from compiler.extractor import generate_skill_id, compute_skill_hash


def test_generate_skill_id():
    assert generate_skill_id("DOCX-Engineering") == "docx-engineering"
    assert generate_skill_id("My_Awesome Skill!!!") == "my-awesome-skill"


def test_compute_skill_hash(tmp_path):
    skill_dir = tmp_path / "skill-a"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("content")
    hash_val = compute_skill_hash(skill_dir)
    assert isinstance(hash_val, str)
    assert len(hash_val) == 64
