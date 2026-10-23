import subprocess
import sys

import pytest


@pytest.mark.parametrize('module', ['probe', 'audit'])
def test_legacy_diagnostic_cli_requires_explicit_config_without_network(module):
    help_result = subprocess.run(
        [sys.executable, '-m', f'alphalab.{module}', '--help'],
        text=True, capture_output=True,
    )
    assert help_result.returncode == 0
    assert 'Legacy optional' in help_result.stdout or 'Legacy optional' in help_result.stderr
    assert 'explicit YAML config' in help_result.stdout or 'explicit YAML config' in help_result.stderr

    result = subprocess.run(
        [sys.executable, '-m', f'alphalab.{module}'],
        text=True, capture_output=True,
    )
    assert result.returncode == 2
    assert '--config' in result.stderr
