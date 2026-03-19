"""Pytest configuration for OntoSkills compiler tests."""
import sys
from pathlib import Path

# Add parent directory to path for imports when running pytest directly
# This is needed because pytest runs from tests/ directory
tests_dir = Path(__file__).parent
compiler_dir = tests_dir.parent
if str(compiler_dir) not in sys.path:
    sys.path.insert(0, str(compiler_dir))
