#!/usr/bin/env bash
# Run from the AlphaLab project root on macOS, after freezing plan and collecting prices.
set -euo pipefail
cd "$(dirname "$0")/.."
python -m pytest -q
python -m alphalab.study_run \
  --plan configs/study_plan.json \
  --selected inputs/universe_selected.csv \
  --snapshots inputs/sina_snapshots \
  --output outputs/study_2026
python scripts/build_research_report.py --results outputs/study_2026 --out outputs/study_2026/public_report
printf '\nResearch report created at outputs/study_2026/public_report.\n'
