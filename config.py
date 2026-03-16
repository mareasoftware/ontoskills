"""Configuration module for OntoClaw compiler.

This module centralizes all configuration settings with environment variable support.
Environment variables allow enterprise deployment with custom namespaces and paths.
"""
import os


# Base URI for the ontology (can be customized via environment)
BASE_URI = os.getenv('ONTOCLAW_BASE_URI', 'http://ontoclaw.marea.software/ontology#')

# Directory paths (relative to project root or absolute)
SKILLS_DIR = os.getenv('ONTOCLAW_SKILLS_DIR', '../../skills/')
OUTPUT_DIR = os.getenv('ONTOCLAW_OUTPUT_DIR', '../../semantic-skills/')

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
