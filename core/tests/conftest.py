"""Pytest configuration for OntoSkills compiler tests."""
import sys
from pathlib import Path

# Add src directory to path for imports when running pytest directly
# This is needed because the package is now in src/
tests_dir = Path(__file__).parent
src_dir = tests_dir.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
