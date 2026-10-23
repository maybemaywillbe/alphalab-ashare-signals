from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'run_end_to_end_mac.sh'


@pytest.mark.parametrize(
    'present,missing_name',
    [
        (set(), 'configs/study_plan.json'),
        ({'configs/study_plan.json'}, 'configs/study_plan.json.sha256'),
        ({'configs/study_plan.json', 'configs/study_plan.json.sha256'},
         'inputs/universe_selected.csv'),
    ],
)
def test_missing_frozen_inputs_stop_before_python_or_network(tmp_path, present, missing_name):
    project = tmp_path / 'project'
    (project / 'scripts').mkdir(parents=True)
    script = project / 'scripts' / 'run_end_to_end_mac.sh'
    script.write_bytes(SCRIPT.read_bytes())
    for relative in present:
        target = project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('placeholder')

    fake_bin = tmp_path / 'bin'
    fake_bin.mkdir()
    python = fake_bin / 'python'
    python.write_text('#!/bin/sh\necho called >> "$PYTHON_CALL_LOG"\nexit 99\n')
    python.chmod(0o755)
    call_log = tmp_path / 'python_calls.log'
    env = os.environ.copy()
    env['PATH'] = f'{fake_bin}:{env["PATH"]}'
    env['PYTHON_CALL_LOG'] = str(call_log)

    result = subprocess.run(['/bin/bash', str(script)], text=True, capture_output=True, env=env)

    assert result.returncode == 2
    assert missing_name in result.stderr
    assert 'Restore the original files from the official AlphaLab release package' in result.stderr
    assert not call_log.exists(), 'Python (including any online candidate fetch) must not run'


def test_end_to_end_script_has_no_candidate_fetch_or_resampling_path():
    source = SCRIPT.read_text()
    assert 'alphalab.collect' not in source
    assert 'study_plan --candidates' not in source
    assert "load_frozen_plan('configs/study_plan.json','inputs/universe_selected.csv')" in source
    assert "plan['target_names'] != 100" in source


@pytest.mark.parametrize('existing_output', [
    'outputs/study_2026',
    'outputs/public_release_ready',
])
def test_existing_outputs_stop_before_python_or_network(tmp_path, existing_output):
    project = tmp_path / 'project'
    (project / 'scripts').mkdir(parents=True)
    script = project / 'scripts' / 'run_end_to_end_mac.sh'
    script.write_bytes(SCRIPT.read_bytes())
    target = project / existing_output
    target.mkdir(parents=True)
    (target / 'keep.txt').write_text('existing user data')

    fake_bin = tmp_path / 'bin'
    fake_bin.mkdir()
    python = fake_bin / 'python'
    python.write_text('#!/bin/sh\necho called >> "$PYTHON_CALL_LOG"\nexit 99\n')
    python.chmod(0o755)
    call_log = tmp_path / 'python_calls.log'
    env = os.environ.copy()
    env['PATH'] = f'{fake_bin}:{env["PATH"]}'
    env['PYTHON_CALL_LOG'] = str(call_log)

    result = subprocess.run(['/bin/bash', str(script)], text=True, capture_output=True, env=env)

    assert result.returncode == 3
    assert existing_output in result.stderr
    assert 'never deletes or overwrites' in result.stderr
    assert not call_log.exists(), 'preflight must stop before tests or any network-capable Python command'
    assert (target / 'keep.txt').read_text() == 'existing user data'
