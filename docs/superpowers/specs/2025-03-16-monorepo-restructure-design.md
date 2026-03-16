# OntoClaw Monorepo Restructure Design

**Created:** 2025-03-16

## Goal

Reorganize the OntoClaw monorepo to cleanly separate the Python ETL compiler from the upcoming Rust MCP server, while keeping data directories (skills, semantic-skills) at the top level for easy access.

## Current State

```
ontoclaw/
├── cli.py, compiler.py, config.py, exceptions.py, extractor.py,
│   loader.py, schemas.py, security.py, sparql.py, transformer.py  # 10 Python files in root
├── skills/                   # Input markdown skills
├── tests/                    # Python tests
├── docs/
└── assets/
```

**Problems:**
- 10 Python files clutter the root
- No clear separation between ETL and future MCP components
- Tests mixed with code at top level

## Proposed Structure

```
ontoclaw/
├── etl/                      # Python ETL compiler
│   ├── src/
│   │   └── ontoclaw_etl/     # Python package
│   │       ├── __init__.py
│   │       ├── cli.py
│   │       ├── compiler.py
│   │       ├── config.py
│   │       ├── exceptions.py
│   │       ├── extractor.py
│   │       ├── loader.py
│   │       ├── schemas.py
│   │       ├── security.py
│   │       ├── sparql.py
│   │       └── transformer.py
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_cli.py
│   │   ├── test_config.py
│   │   ├── test_exceptions.py
│   │   ├── test_extractor.py
│   │   ├── test_loader.py
│   │   ├── test_schemas.py
│   │   ├── test_security.py
│   │   ├── test_sparql.py
│   │   ├── test_transformer.py
│   │   └── test_integration.py
│   ├── pyproject.toml
│   └── README.md
│
├── mcp/                      # Rust MCP server (placeholder)
│   └── README.md             # "Coming soon"
│
├── skills/                   # Input: markdown skills
│   └── office/public/
│       ├── docx/SKILL.md
│       ├── pdf/SKILL.md
│       ├── pptx/SKILL.md
│       └── xlsx/SKILL.md
│
├── semantic-skills/          # Output: compiled ontology
│   ├── ontoclaw-core.ttl
│   ├── index.ttl
│   └── office/public/*/skill.ttl
│
├── docs/                     # Documentation
│   └── superpowers/
│       ├── specs/
│       └── plans/
│
├── assets/
│   └── logo.png
│
├── .planning/                # GSD planning
├── .gitignore
├── .env
├── README.md                 # Monorepo root README
└── LICENSE
```

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| `etl/src/ontoclaw_etl/` package | Follows Python src-layout best practices, prevents import issues |
| `etl/tests/` inside component | Tests co-located with code, easier isolation |
| `etl/pyproject.toml` | Independent versioning, can be published to PyPI separately |
| `mcp/` placeholder | Ready for Rust implementation, clear intent |
| `skills/` at root | Data directory, accessible from both ETL and MCP |
| `semantic-skills/` at root | Output data, same rationale as skills/ |

## pyproject.toml Updates

```toml
# etl/pyproject.toml
[project]
name = "ontoclaw-etl"
version = "0.2.0"
description = "Python ETL compiler for OntoClaw skills to OWL 2 ontology"
packages = [{from = "src", include = "ontoclaw_etl"}]

[project.scripts]
ontoclaw = "ontoclaw_etl.cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "integration: marks tests as integration tests",
]
addopts = "-m 'not integration'"
```

## Migration Steps

1. Create `etl/src/ontoclaw_etl/` directory structure
2. Move all `.py` files (except `__init__.py`) to `etl/src/ontoclaw_etl/`
3. Move `tests/` to `etl/tests/`
4. Create `etl/pyproject.toml` with updated paths
5. Create `etl/README.md` (move ETL-specific docs)
6. Update all imports from `from X import` to `from ontoclaw_etl.X import`
7. Update root README.md for monorepo overview
8. Create `mcp/README.md` placeholder
9. Verify tests pass: `cd etl && pytest`
10. Commit

## Benefits

- **Clean root** - Only data directories and docs at top level
- **Isolation** - ETL can be developed/tested/published independently
- **Extensibility** - MCP ready for Rust implementation
- **Clarity** - Clear separation: code in `etl/`, data in `skills/` and `semantic-skills/`

## Success Criteria

- [ ] All Python files moved to `etl/src/ontoclaw_etl/`
- [ ] All tests moved to `etl/tests/`
- [ ] All 72 unit tests pass
- [ ] Integration tests pass with `pytest -m integration`
- [ ] `ontoclaw compile` works from command line
- [ ] Root directory has <5 non-config files
