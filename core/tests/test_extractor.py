from compiler.extractor import generate_skill_id, generate_qualified_skill_id, compute_skill_hash, generate_sub_skill_id, compute_sub_skill_hash, normalize_package_id


def test_normalize_package_id():
    # Already normalized
    assert normalize_package_id("obra/superpowers") == "obra/superpowers"
    assert normalize_package_id("local") == "local"

    # NPM scoped package
    assert normalize_package_id("@scope/package-name") == "scope/package-name"

    # Uppercase
    assert normalize_package_id("MyCompany/MyPackage") == "mycompany/mypackage"

    # Dots and special chars
    assert normalize_package_id("my.company/my.package") == "my-company/my-package"
    assert normalize_package_id("my_company/my_package") == "my-company/my-package"

    # Spaces
    assert normalize_package_id("My Company/My Package") == "my-company/my-package"

    # Multiple slashes (nested packages)
    assert normalize_package_id("owner/repo/pkg") == "owner/repo/pkg"

    # Mixed issues
    assert normalize_package_id("@MyScope/My.Package") == "myscope/my-package"

    # Empty segments fall back to local
    assert normalize_package_id("///") == "local"
    assert normalize_package_id("") == "local"


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


def test_generate_qualified_skill_id():
    assert generate_qualified_skill_id("obra/superpowers", "brainstorming") == "obra/superpowers/brainstorming"
    assert generate_qualified_skill_id("local", "my-skill") == "local/my-skill"
    assert generate_qualified_skill_id("owner/repo/pkg", "skill") == "owner/repo/pkg/skill"


def test_generate_sub_skill_id():
    # Basic case
    assert generate_sub_skill_id("obra/superpowers", "brainstorming", "planning.md") == "obra/superpowers/brainstorming/planning"

    # Filename with special chars
    assert generate_sub_skill_id("obra/superpowers", "brainstorming", "my-planning.md") == "obra/superpowers/brainstorming/my-planning"

    # Nested package
    assert generate_sub_skill_id("owner/repo", "skill", "sub.md") == "owner/repo/skill/sub"


def test_resolve_package_id_with_manifest(tmp_path):
    from compiler.extractor import resolve_package_id

    # Create skill directory with package.json
    skill_dir = tmp_path / "skills" / "brainstorming"
    skill_dir.mkdir(parents=True)

    package_json = tmp_path / "skills" / "package.json"
    package_json.write_text('{"name": "obra/superpowers", "version": "1.0.0"}')

    result = resolve_package_id(skill_dir)
    assert result == "obra/superpowers"


def test_resolve_package_id_fallback_local(tmp_path):
    from compiler.extractor import resolve_package_id

    # No manifest, should return "local"
    skill_dir = tmp_path / "skills" / "some-skill"
    skill_dir.mkdir(parents=True)

    result = resolve_package_id(skill_dir)
    assert result == "local"


def test_resolve_package_id_with_toml_manifest(tmp_path):
    from compiler.extractor import resolve_package_id

    # Create skill directory with ontoskills.toml in parent
    skill_dir = tmp_path / "skills" / "brainstorming"
    skill_dir.mkdir(parents=True)

    toml_file = tmp_path / "skills" / "ontoskills.toml"
    toml_file.write_text('name = "obra/superpowers"\nversion = "1.0.0"')

    result = resolve_package_id(skill_dir)
    assert result == "obra/superpowers"


def test_compute_sub_skill_hash(tmp_path):
    md_file = tmp_path / "planning.md"
    md_file.write_text("# Planning Sub-Skill\n\nContent here")

    hash_val = compute_sub_skill_hash(md_file)
    assert isinstance(hash_val, str)
    assert len(hash_val) == 64


def test_compute_sub_skill_hash_independence(tmp_path):
    """Hash is independent of parent - only file content matters."""
    md_file = tmp_path / "test.md"
    md_file.write_text("same content")

    hash1 = compute_sub_skill_hash(md_file)

    # Same content, same hash
    md_file2 = tmp_path / "test2.md"
    md_file2.write_text("same content")
    hash2 = compute_sub_skill_hash(md_file2)

    assert hash1 == hash2
