"""Tests for config.py module."""
import os
import pytest
from unittest.mock import patch


def test_default_base_uri():
    """Verify default BASE_URI when environment variable is not set."""
    # Ensure the env var is not set
    with patch.dict(os.environ, {}, clear=False):
        # Remove ONTOSKILLS_BASE_URI if it exists
        os.environ.pop('ONTOSKILLS_BASE_URI', None)

        # Need to reload the config module to pick up new env vars
        import importlib
        from compiler import config
        importlib.reload(config)

        assert config.BASE_URI == 'https://ontoskills.sh/ontology#'


def test_custom_base_uri():
    """Verify custom BASE_URI value from environment variable."""
    custom_uri = 'http://custom.example.org/ontology#'

    with patch.dict(os.environ, {'ONTOSKILLS_BASE_URI': custom_uri}):
        import importlib
        from compiler import config
        importlib.reload(config)

        assert config.BASE_URI == custom_uri


def test_default_paths():
    """Verify default SKILLS_DIR and OUTPUT_DIR when env vars not set."""
    with patch.dict(os.environ, {}, clear=False):
        # Remove path env vars if they exist
        os.environ.pop('ONTOSKILLS_SKILLS_DIR', None)
        os.environ.pop('ONTOSKILLS_OUTPUT_DIR', None)

        import importlib
        from compiler import config
        importlib.reload(config)

        # Paths are now absolute, resolved from PROJECT_ROOT
        assert config.SKILLS_DIR.endswith('/skills')
        assert config.OUTPUT_DIR.endswith('/ontoskills')


def test_custom_skills_dir():
    """Verify custom SKILLS_DIR from environment variable."""
    custom_dir = '/custom/skills/path/'

    with patch.dict(os.environ, {'ONTOSKILLS_SKILLS_DIR': custom_dir}):
        import importlib
        from compiler import config
        importlib.reload(config)

        assert config.SKILLS_DIR == custom_dir


def test_custom_output_dir():
    """Verify custom OUTPUT_DIR from environment variable."""
    custom_dir = '/custom/output/path/'

    with patch.dict(os.environ, {'ONTOSKILLS_OUTPUT_DIR': custom_dir}):
        import importlib
        from compiler import config
        importlib.reload(config)

        assert config.OUTPUT_DIR == custom_dir


def test_default_anthropic_model():
    """Verify ANTHROPIC_MODEL is configured (from env var or hardcoded default)."""
    from compiler import config
    assert config.ANTHROPIC_MODEL is not None
    assert isinstance(config.ANTHROPIC_MODEL, str)


def test_custom_anthropic_model():
    """Verify custom ANTHROPIC_MODEL from environment variable."""
    custom_model = 'claude-3-opus-20250201'

    with patch.dict(os.environ, {'ANTHROPIC_MODEL': custom_model}):
        import importlib
        from compiler import config
        importlib.reload(config)

        assert config.ANTHROPIC_MODEL == custom_model


def test_default_security_model():
    """Verify SECURITY_MODEL is configured (from env var or hardcoded default)."""
    from compiler import config
    assert config.SECURITY_MODEL is not None
    assert isinstance(config.SECURITY_MODEL, str)


def test_custom_security_model():
    """Verify custom SECURITY_MODEL from environment variable."""
    custom_model = 'claude-3-haiku-20250301'

    with patch.dict(os.environ, {'SECURITY_MODEL': custom_model}):
        import importlib
        from compiler import config
        importlib.reload(config)

        assert config.SECURITY_MODEL == custom_model


def test_max_iterations_constant():
    """Verify MAX_ITERATIONS is set correctly."""
    from compiler import config
    assert config.MAX_ITERATIONS == 20


def test_extraction_timeout_constant():
    """Verify EXTRACTION_TIMEOUT is set correctly."""
    from compiler import config
    assert config.EXTRACTION_TIMEOUT == 120


def test_core_states_dict():
    """Verify CORE_STATES contains all required states."""
    from compiler import config

    expected_states = [
        'SystemAuthenticated',
        'NetworkAvailable',
        'FileExists',
        'DirectoryWritable',
        'APIKeySet',
        'ToolInstalled',
        'EnvironmentReady'
    ]

    for state in expected_states:
        assert state in config.CORE_STATES
        assert isinstance(config.CORE_STATES[state], str)
        # Check that it's a valid URI fragment
        assert config.CORE_STATES[state].startswith('#')


def test_failure_states_dict():
    """Verify FAILURE_STATES contains all required states."""
    from compiler import config

    expected_states = [
        'PermissionDenied',
        'NetworkTimeout',
        'FileNotFound',
        'InvalidInput',
        'OperationFailed'
    ]

    for state in expected_states:
        assert state in config.FAILURE_STATES
        assert isinstance(config.FAILURE_STATES[state], str)
        # Check that it's a valid URI fragment
        assert config.FAILURE_STATES[state].startswith('#')


def test_default_skills_author():
    """Verify DEFAULT_SKILLS_AUTHOR is set or None."""
    from compiler import config
    assert config.DEFAULT_SKILLS_AUTHOR is None or isinstance(config.DEFAULT_SKILLS_AUTHOR, str)


def test_custom_skills_author():
    """Verify custom DEFAULT_SKILLS_AUTHOR from environment variable."""
    with patch.dict(os.environ, {'DEFAULT_SKILLS_AUTHOR': 'mareasw'}):
        import importlib
        from compiler import config
        importlib.reload(config)
        assert config.DEFAULT_SKILLS_AUTHOR == 'mareasw'
