"""No-network frozen-plan tests; use purposely shuffled candidate stock codes."""
from pathlib import Path
import pandas as pd
import pytest
from alphalab.study_plan import (classify, select_universe, freeze_plan, load_frozen_plan, file_sha256)


def source_csv(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    symbols = ([f'600{i:03d}' for i in range(26)]
               + [f'000{i:03d}' for i in range(26)]
               + [f'300{i:03d}' for i in range(12)]
               + [f'688{i:03d}' for i in range(6)])
    frame = pd.DataFrame({'symbol': symbols[::-1], 'listed_on': '', 'delisted_on': '',
                          'source': 'synthetic current-listed fixture', 'verified': 'false'})
    dest = folder / 'candidate.csv'
    frame.to_csv(dest, index=False)
    return dest


def test_stratified_deterministic_and_not_code_order(tmp_path):
    path = source_csv(tmp_path)
    selected = select_universe(path, target=40, seed=42)
    assert len(selected) == 40
    assert selected.groupby('stratum').size().to_dict() == {'sh_main': 16, 'sz_main': 16, 'chinext': 6, 'star': 2}
    assert selected.symbol.tolist() == select_universe(path, target=40, seed=42).symbol.tolist()
    assert set(selected.symbol) != set(pd.read_csv(path, dtype=str).symbol.iloc[:40])
    assert set(selected.symbol) != set(select_universe(path, target=40, seed=43).symbol)
    assert classify('688001') == 'star' and classify('430001') is None


def test_freeze_and_refuse_change(tmp_path):
    src = source_csv(tmp_path)
    plan_path, selected_path = tmp_path/'plan.json', tmp_path/'selected.csv'
    p = freeze_plan(src, plan_path, selected_path, target=40, seed=1)
    assert load_frozen_plan(plan_path, selected_path) == p
    with pytest.raises(FileExistsError):
        freeze_plan(src, plan_path, selected_path, target=40)
    selected_path.write_text(selected_path.read_text() + '\n')
    with pytest.raises(ValueError, match='changed'):
        load_frozen_plan(plan_path, selected_path)


def test_insufficient_stratum_refused(tmp_path):
    src = source_csv(tmp_path)
    with pytest.raises(ValueError, match='need'):
        select_universe(src, target=100)
