"""Configuration module for OntoClaw compiler.

This module centralizes all configuration settings with environment variable support.
Environment variables allow enterprise deployment with custom namespaces and paths.
"""
import os
from pathlib import Path

from compiler.env import load_local_env


load_local_env()


# Project root (parent of core/ directory where this file lives)
PROJECT_ROOT = Path(__file__).parent.parent.resolve()

# Base URI for the ontology (can be customized via environment)
BASE_URI = os.getenv(
    'ONTOCLAW_BASE_URI',
    os.getenv('ONTOSKILLS_BASE_URI', 'http://ontoclaw.marea.software/ontology#')
)

# Directory paths (relative to project root by default)
SKILLS_DIR = os.getenv(
    'ONTOCLAW_SKILLS_DIR',
    os.getenv('ONTOSKILLS_SKILLS_DIR', str(PROJECT_ROOT / 'skills'))
)
ONTOLOGY_ROOT = os.getenv(
    'ONTOCLAW_ONTOLOGY_ROOT',
    os.getenv('ONTOSKILLS_OUTPUT_DIR', str(PROJECT_ROOT / 'ontoskills'))
)
OUTPUT_DIR = os.getenv(
    'ONTOCLAW_OUTPUT_DIR',
    os.getenv('ONTOSKILLS_OUTPUT_DIR', ONTOLOGY_ROOT)
)
ONTOLOGY_SYSTEM_DIR = str(Path(ONTOLOGY_ROOT) / 'system')
SKILLS_VENDOR_DIR = str(Path(SKILLS_DIR) / 'vendor')
ONTOLOGY_VENDOR_DIR = str(Path(ONTOLOGY_ROOT) / 'vendor')


def resolve_ontology_root(path: str | Path) -> Path:
    """Resolve the ontology root from a direct root path or one of its subtrees."""
    candidate = Path(path).resolve()
    configured_root = Path(ONTOLOGY_ROOT).resolve()
    if configured_root == candidate or configured_root in candidate.parents:
        return configured_root
    for parent in (candidate, *candidate.parents):
        if parent.name == 'ontoskills':
            return parent
    return candidate

# Anthropic API model configurations
ANTHROPIC_MODEL = os.getenv('ANTHROPIC_MODEL', 'claude-opus-4-6')
SECURITY_MODEL = os.getenv('SECURITY_MODEL', 'claude-opus-4-6')

# Processing limits
MAX_ITERATIONS = 20
EXTRACTION_TIMEOUT = 120  # seconds

# Core state definitions (URI fragments that will be appended to BASE_URI)
CORE_STATES = {
    'SystemAuthenticated': '#SystemAuthenticated',
    'NetworkAvailable': '#NetworkAvailable',
    'FileExists': '#FileExists',
    'DirectoryWritable': '#DirectoryWritable',
    'APIKeySet': '#APIKeySet',
    'ToolInstalled': '#ToolInstalled',
    'EnvironmentReady': '#EnvironmentReady',
}

# Failure state definitions
FAILURE_STATES = {
    'PermissionDenied': '#PermissionDenied',
    'NetworkTimeout': '#NetworkTimeout',
    'FileNotFound': '#FileNotFound',
    'InvalidInput': '#InvalidInput',
    'OperationFailed': '#OperationFailed',
}
