#!/usr/bin/env bash
# Reproduce the published frozen-sample study; this script never creates a new universe.
set -euo pipefail
cd "$(dirname "$0")/.."

# Refuse conflicts before pytest, calendar collection, or price downloads.
for path in outputs/study_2026 outputs/public_release_ready; do
  if [[ -e "$path" ]]; then
    printf 'ERROR: output path already exists: %s\n' "$path" >&2
    printf 'Move or rename it manually before running; this workflow never deletes or overwrites existing outputs.\n' >&2
    exit 3
  fi
done

required=(
  configs/study_plan.json
  configs/study_plan.json.sha256
  inputs/universe_selected.csv
)
missing=()
for path in "${required[@]}"; do
  [[ -f "$path" ]] || missing+=("$path")
done
if ((${#missing[@]})); then
  printf 'ERROR: frozen research inputs are incomplete.\n' >&2
  printf 'Missing: %s\n' "${missing[@]}" >&2
  printf 'Restore the original files from the official AlphaLab release package, preserving their paths; do not regenerate or resample the universe.\n' >&2
  exit 2
fi

python -m pytest -q
python - <<'PY'
from alphalab.study_plan import load_frozen_plan
plan=load_frozen_plan('configs/study_plan.json','inputs/universe_selected.csv')
if plan['target_names'] != 100:
    raise ValueError('Frozen plan must contain exactly 100 selected stocks')
print('Frozen design verified; no new candidate list or sample was created.')
PY
if [[ ! -f inputs/sina_snapshots/exchange_calendar.csv ]]; then
  python -m alphalab.trading_calendar --out inputs/sina_snapshots/exchange_calendar.csv \
    --start 2014-01-01 --end 2026-10-23
fi
python -m alphalab.sina_unified --universe inputs/universe_selected.csv \
  --snapshots inputs/sina_snapshots --start 20140101 --end 20261023
python -m alphalab.study_run --snapshots inputs/sina_snapshots \
  --plan configs/study_plan.json --selected inputs/universe_selected.csv \
  --output outputs/study_2026
python scripts/build_research_report.py --results outputs/study_2026 \
  --out outputs/study_2026/public_report
python scripts/prepare_public_release.py --results outputs/study_2026 \
  --destination outputs/public_release_ready
printf '\nStudy report and release package created at outputs/study_2026/public_report and outputs/public_release_ready/AlphaLab.\n'
